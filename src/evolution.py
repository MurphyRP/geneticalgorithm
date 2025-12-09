"""
Evolution Orchestrator - Genetic Algorithm Workflow Coordination

This module coordinates the genetic algorithm's evolution process, orchestrating
all GA operators (selection, crossover, mutation, immigration) to evolve from
one generation to the next.

Key Components:
- evolve_generation(): Main orchestrator for Gen N → Gen N+1 transition
- run_evolution(): Placeholder for multi-generation loop (Phase 10)
- Helper functions for database queries and statistics

Architecture Context:
This is the "construction foreman" that coordinates all the individual GA operator
"tools" (selection, mutation, crossover, immigration) built in previous phases.
Without this orchestrator, the operators are isolated functions with no workflow.

Used by: Main evolution scripts, testing scripts, analysis tools
Creates: Next generation populations, evolution statistics
Related: ga_operators.py (selection, mutation, crossover, immigration)
         fitness_evaluator.py (fitness calculation pipeline)
         couchbase_client.py (database operations)
"""

import time
import random
import statistics
import math
from datetime import datetime
from typing import List, Dict, Optional
from scipy import stats as scipy_stats

from src.models import Prompt
from src.couchbase_client import CouchbaseClient
from src.ga_operators import select_elite, mutate_prompt, crossover, create_immigrant
from src.fitness_evaluator import evaluate_prompt_fitness


def load_generation(
    cb: CouchbaseClient,
    era: str,
    generation: int
) -> List[Prompt]:
    """
    Load all prompts from a specific generation.

    Queries the 'generations' collection and deserializes results into Prompt objects.

    IMPORTANT DATA MODEL NOTE:
    The 'generations' collection in Couchbase contains ALL prompts from ALL generations
    (Generation 0, 1, 2, ..., N) for all eras. Each prompt document includes its
    generation number and era as fields, allowing us to query specific generations.
    See models.py for the complete Prompt data structure.

    Args:
        cb: Connected CouchbaseClient instance
        era: Era identifier (e.g., "test-1", "mixed-1")
        generation: Generation number to load

    Returns:
        List of Prompt objects from the specified generation

    Raises:
        ValueError: If no prompts found for the specified era/generation
    """
    query = f"""
        SELECT g.* FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` g
        WHERE g.era = '{era}' AND g.generation = {generation}
    """

    results = cb.cluster.query(query)
    prompts = [Prompt.from_dict(row) for row in results]

    if len(prompts) == 0:
        raise ValueError(f"No prompts found for era={era}, generation={generation}")

    return prompts


def get_random_suitable_chunk(cb: CouchbaseClient) -> Dict:
    """
    Fetch a random suitable chunk from the unstructured corpus.

    Queries chunks that have been rated as suitable for compression testing
    and fall within the target word count range.

    Args:
        cb: Connected CouchbaseClient instance

    Returns:
        Dict with 'chunk_id', 'text', 'word_count' keys

    Raises:
        ValueError: If no suitable chunks found
    """
    query = f"""
        SELECT chunk_id, text, word_count
        FROM `{cb.bucket_name}`.`{cb.scope_name}`.`unstructured`
        WHERE suitable_for_compression_testing = true
        AND word_count BETWEEN 550 AND 650
        ORDER BY RANDOM()
        LIMIT 1
    """

    results = cb.cluster.query(query)
    rows = list(results)

    if len(rows) == 0:
        raise ValueError(
            "No suitable chunks found in unstructured collection. "
            "Run corpus evaluation first to rate chunks."
        )

    return rows[0]


def calculate_generation_stats(
    prompts: List[Prompt],
    era: str,
    generation: int,
    elite_count: int,
    crossover_count: int,
    mutation_count: int,
    immigrant_count: int,
    evaluated_count: int,
    elapsed_seconds: float,
    evaluation_corpus_ids: List[str],
    fitness_metric: str = "words",
    compression_model: str = "claude",
    prompt_temperature: float = 1.0,
    single_tag: bool = False
) -> Dict:
    """
    Calculate generation-level statistics for visualization and analysis.

    Computes fitness metrics (mean, std, median, min, max) and tracks
    population composition (elite, crossover, mutation, immigrant counts).

    These statistics enable gradient visualization without querying all prompts
    and are critical for Paper 1 results analysis.

    Args:
        prompts: All prompts in the generation
        era: Era identifier
        generation: Generation number
        elite_count: Number of elite prompts
        crossover_count: Number of crossover children
        mutation_count: Number of mutation children
        immigrant_count: Number of immigrants
        evaluated_count: Number of prompts actually evaluated (should be children only)
        elapsed_seconds: Time taken for generation evolution
        evaluation_corpus_ids: List of chunk IDs used in evaluation corpus
        fitness_metric: Metric used for fitness ("tokens" or "words")
        compression_model: Model used for compression ("openai", "claude", "gemini")

    Returns:
        Dictionary with generation statistics:
        - Population composition (elite/crossover/mutation/immigrant counts)
        - Fitness metrics (mean/std/median/min/max)
        - Timing information
        - Metadata (era, generation, population_size)
        - Evaluation corpus IDs for reproducibility
        - Fitness evaluation metadata (fitness_metric, compression_model)
    """
    # Extract fitness scores (filter out None values)
    fitness_scores = [p.fitness for p in prompts if p.fitness is not None]

    # Validate we have fitness data
    if len(fitness_scores) == 0:
        raise ValueError("No fitness scores found in generation - all prompts have fitness=None")

    # Calculate statistics
    stats = {
        "era": era,
        "generation": generation,
        "population_size": len(prompts),
        "mean_fitness": statistics.mean(fitness_scores),
        "std_fitness": statistics.stdev(fitness_scores) if len(fitness_scores) > 1 else 0.0,
        "median_fitness": statistics.median(fitness_scores),
        "min_fitness": min(fitness_scores),
        "max_fitness": max(fitness_scores),
        "elite_count": elite_count,
        "crossover_count": crossover_count,
        "mutation_count": mutation_count,
        "immigrant_count": immigrant_count,
        "evaluated_count": evaluated_count,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "evaluation_corpus_ids": evaluation_corpus_ids,
        "fitness_metric": fitness_metric,
        "compression_model": compression_model,
        "prompt_temperature": prompt_temperature,
        "single_tag": single_tag
    }

    return stats


def store_generation_stats(
    era: str,
    generation: int,
    stats: Dict,
    couchbase_client: CouchbaseClient,
    current_generation_prompts: Optional[List[Prompt]] = None,
    previous_generation_prompts: Optional[List[Prompt]] = None
) -> None:
    """
    Store generation statistics to database for visualization and analysis.

    Saves statistics to the 'generation_stats' collection with document ID
    in format: {era}-gen-{generation}. Includes statistical significance tests
    (t-test vs previous generation, ANOVA across all generations) for Paper 1 analysis.

    Statistical Tests:
    - T-test: Compare Gen N vs Gen N-1 (requires previous_generation_prompts)
    - ANOVA: Compare all generations Gen 0 through N (requires 3+ generations)

    Args:
        era: Era identifier (e.g., "test-1", "mixed-1")
        generation: Generation number
        stats: Statistics dict from evolve_generation() or calculate_generation_stats()
        couchbase_client: Connected CouchbaseClient instance
        current_generation_prompts: Optional list of current generation prompts for t-test
        previous_generation_prompts: Optional list of previous generation prompts for t-test

    Raises:
        Exception: If database save fails (fail-loud)

    Used by: run_evolution() after each generation
    Creates: Document in 'generation_stats' collection
    Related: calculate_generation_stats(), evolve_generation()
    """
    # Create document with all statistics
    generation_doc = {
        "generation_id": f"{era}-gen-{generation}",
        "era": era,
        "generation": generation,
        "mean_fitness": stats["mean_fitness"],
        "std_fitness": stats["std_fitness"],
        "median_fitness": stats["median_fitness"],
        "min_fitness": stats["min_fitness"],
        "max_fitness": stats["max_fitness"],
        "elite_count": stats["elite_count"],
        "crossover_count": stats["crossover_count"],
        "mutation_count": stats["mutation_count"],
        "immigrant_count": stats["immigrant_count"],
        "evaluated_count": stats["evaluated_count"],
        "elapsed_seconds": stats["elapsed_seconds"],
        "population_size": stats["population_size"],
        "evaluation_corpus_ids": stats["evaluation_corpus_ids"],
        "prompt_temperature": stats.get("prompt_temperature", 1.0),
        "single_tag": stats.get("single_tag", False),
        "timestamp": datetime.now().isoformat()  # Temporal tracking
    }

    # Compute statistical tests if data available
    if current_generation_prompts and previous_generation_prompts:
        ttest_result = compute_ttest_vs_previous(current_generation_prompts, previous_generation_prompts)
        if ttest_result:
            generation_doc["ttest_vs_previous"] = ttest_result

    # ANOVA across all generations (only if 3+ generations exist)
    if generation >= 2:
        anova_result = compute_anova_generations(era, generation, couchbase_client)
        if anova_result:
            generation_doc["anova_generations"] = anova_result

    # Save to generation_stats collection (not generations - that's for prompts)
    try:
        couchbase_client.save_document("generation_stats", generation_doc["generation_id"], generation_doc)
    except Exception as e:
        print(f"❌ CRITICAL ERROR storing generation_stats for {era} Gen {generation}: {e}")
        raise  # Fail loud - statistics are critical for research


def create_era(
    era: str,
    compression_model: str,
    population_size: int,
    elite_fraction: float,
    mutation_fraction: float,
    immigration_fraction: float,
    tags_per_mutation: int,
    single_tag: bool,
    couchbase_client: CouchbaseClient
) -> None:
    """
    Create era document to track experiment configuration.

    Stores experiment metadata and configuration in the 'eras' collection.
    This enables tracking what parameters were used for each experimental run
    and provides a registry of all experiments.

    Args:
        era: Era identifier (e.g., "test-1", "mixed-1")
        compression_model: Model used for compression
        population_size: Number of prompts per generation
        elite_fraction: Fraction of population to preserve as elite
        mutation_fraction: Fraction of population to create via mutation
        immigration_fraction: Fraction of population to create via immigration (odd gens)
        tags_per_mutation: Number of tags to mutate per prompt
        couchbase_client: Connected CouchbaseClient instance
    """
    era_doc = {
        "era": era,
        "compression_model": compression_model,
        "population_size": population_size,
        "elite_fraction": elite_fraction,
        "mutation_fraction": mutation_fraction,
        "immigration_fraction": immigration_fraction,
        "tags_per_mutation": tags_per_mutation,
        "single_tag": single_tag,
        "status": "running",
        "start_time": datetime.now().isoformat(),
        "end_time": None,
        "total_generations": 0,
        "final_mean_fitness": None,
        "final_max_fitness": None
    }

    couchbase_client.save_document("eras", era, era_doc)


def update_era_completion(
    era: str,
    total_generations: int,
    final_mean_fitness: float,
    final_max_fitness: float,
    couchbase_client: CouchbaseClient
) -> None:
    """
    Update era document when experiment completes.

    Marks experiment as complete and records final statistics.

    Args:
        era: Era identifier
        total_generations: Total number of generations evolved
        final_mean_fitness: Mean fitness of final generation
        final_max_fitness: Max fitness of final generation
        couchbase_client: Connected CouchbaseClient instance
    """
    era_doc = couchbase_client.get_document("eras", era)
    era_doc["status"] = "completed"
    era_doc["end_time"] = datetime.now().isoformat()
    era_doc["total_generations"] = total_generations
    era_doc["final_mean_fitness"] = final_mean_fitness
    era_doc["final_max_fitness"] = final_max_fitness

    couchbase_client.save_document("eras", era, era_doc)


def compute_ttest_vs_previous(
    current_generation: List[Prompt],
    previous_generation: List[Prompt]
) -> Optional[Dict]:
    """
    Compute t-test comparing current vs previous generation fitness.

    Tests null hypothesis: "Mean fitness has not improved"
    A significant result (p < 0.05) indicates genuine improvement.

    Args:
        current_generation: List of prompts in current generation
        previous_generation: List of prompts in previous generation

    Returns:
        Dictionary with t-test results, or None if insufficient data
    """
    current_fitness = [p.fitness for p in current_generation if p.fitness is not None]
    previous_fitness = [p.fitness for p in previous_generation if p.fitness is not None]

    if len(current_fitness) < 2 or len(previous_fitness) < 2:
        return None

    # Independent samples t-test (one-tailed, testing for improvement)
    t_stat, p_value_two_tailed = scipy_stats.ttest_ind(current_fitness, previous_fitness)
    p_value = p_value_two_tailed / 2  # One-tailed (testing improvement only)

    # Cohen's d effect size
    pooled_std = ((statistics.stdev(current_fitness) + statistics.stdev(previous_fitness)) / 2)
    cohens_d = (statistics.mean(current_fitness) - statistics.mean(previous_fitness)) / pooled_std if pooled_std > 0 else 0

    return {
        "p_value": float(p_value),
        "significant": bool(p_value < 0.05),  # Convert to Python bool
        "mean_improvement": float(statistics.mean(current_fitness) - statistics.mean(previous_fitness)),
        "effect_size": float(cohens_d),
        "t_statistic": float(t_stat)
    }


def compute_anova_generations(
    era: str,
    current_generation_num: int,
    couchbase_client: CouchbaseClient
) -> Optional[Dict]:
    """
    Compute ANOVA comparing fitness across ALL generations (Gen 0 through current).

    Tests null hypothesis: "Mean fitness is the same across all generations"
    A significant result indicates fitness has changed over evolutionary time.

    Only runs when there are 3+ generations (need at least 3 groups for meaningful ANOVA).

    Args:
        era: Era identifier
        current_generation_num: Current generation number
        couchbase_client: Connected CouchbaseClient instance

    Returns:
        Dictionary with ANOVA results, or None if < 3 generations
    """
    if current_generation_num < 2:
        return None  # Need at least 3 generations (0, 1, 2) for ANOVA

    # Load fitness for all generations from Gen 0 to current
    generation_groups = []
    generation_means = {}

    for gen_num in range(current_generation_num + 1):
        try:
            prompts = load_generation(couchbase_client, era, gen_num)
            fitness_values = [p.fitness for p in prompts if p.fitness is not None]

            if len(fitness_values) >= 2:  # Need at least 2 samples per group
                generation_groups.append(fitness_values)
                generation_means[f"gen_{gen_num}"] = statistics.mean(fitness_values)
        except ValueError:
            # Generation doesn't exist or has no data
            continue

    if len(generation_groups) < 3:
        return None  # Need at least 3 generations for ANOVA

    # Run one-way ANOVA across all generations
    f_stat, p_value = scipy_stats.f_oneway(*generation_groups)

    return {
        "p_value": float(p_value),
        "significant": bool(p_value < 0.05),  # Convert to Python bool
        "f_statistic": float(f_stat),
        "generation_means": {k: float(v) for k, v in generation_means.items()},  # Ensure floats
        "num_generations": int(len(generation_groups))  # Ensure int
    }


def validate_ga_parameters(
    population_size: int,
    elite_fraction: float,
    mutation_fraction: float,
    immigration_fraction: float
) -> None:
    """
    Validate GA parameters before running evolution.

    Ensures fractions don't exceed 1.0 and population is large enough
    to support all genetic operators. Prevents configuration errors that
    would cause generation evolution to fail.

    Args:
        population_size: Total prompts per generation
        elite_fraction: Fraction to keep as elite (0.0-0.5]
        mutation_fraction: Fraction to create via mutation [0.0-0.5]
        immigration_fraction: Fraction to add as immigrants [0.0-0.3]

    Raises:
        ValueError: If parameters are invalid or incompatible

    Example:
        >>> validate_ga_parameters(20, 0.2, 0.2, 0.08)  # OK
        >>> validate_ga_parameters(3, 0.2, 0.2, 0.08)   # ValueError: too small
        >>> validate_ga_parameters(20, 0.5, 0.4, 0.2)   # ValueError: sum > 1.0
    """
    # Population size checks
    if population_size < 5:
        raise ValueError(f"population_size must be >= 5 for meaningful evolution, got {population_size}")

    # Fraction bounds checks
    if not (0.0 < elite_fraction <= 0.5):
        raise ValueError(f"elite_fraction must be in (0.0, 0.5], got {elite_fraction}")

    if not (0.0 <= mutation_fraction <= 0.5):
        raise ValueError(f"mutation_fraction must be in [0.0, 0.5], got {mutation_fraction}")

    if not (0.0 <= immigration_fraction <= 0.3):
        raise ValueError(f"immigration_fraction must be in [0.0, 0.3], got {immigration_fraction}")

    # Sum check (worst case: odd generation with immigration)
    max_fraction = elite_fraction + mutation_fraction + immigration_fraction
    if max_fraction >= 1.0:
        raise ValueError(
            f"Sum of fractions too high ({max_fraction:.2f} >= 1.0). "
            f"elite={elite_fraction}, mutation={mutation_fraction}, immigration={immigration_fraction}. "
            f"Must leave room for crossover!"
        )

    # Check minimum counts make sense
    elite_count = int(population_size * elite_fraction)
    mutation_count = int(population_size * mutation_fraction)
    immigrant_count = math.ceil(population_size * immigration_fraction)

    if elite_count < 1:
        raise ValueError(f"elite_fraction too low: produces 0 elite for population={population_size}")

    min_crossover = population_size - elite_count - mutation_count - immigrant_count
    if min_crossover < 1:
        raise ValueError(
            f"Parameters leave no room for crossover! "
            f"pop={population_size}, elite={elite_count}, mutation={mutation_count}, "
            f"immigrant={immigrant_count}, crossover would be {min_crossover}"
        )


def has_converged(
    all_stats: List[Dict],
    window: int = 3,
    threshold: float = 0.05
) -> bool:
    """
    Check if evolution has converged (fitness plateau detected).

    Convergence criterion: Maximum change in mean fitness over the last
    `window` generations is less than `threshold`.

    Why convergence detection matters:
    - Saves time (don't run 20 gens if converged at 12)
    - Saves API costs (~$4-8 per generation)
    - Scientifically valid stopping criterion
    - Indicates fitness descent is complete

    The sliding window approach ensures we don't stop on temporary plateaus
    but do stop when fitness truly stabilizes.

    Args:
        all_stats: List of generation statistics dicts
        window: Generations to look back (default 3)
        threshold: Max mean fitness change to be considered converged (default 0.05)

    Returns:
        True if converged (fitness plateau detected), False otherwise

    Example:
        Gen 10: mean=15.2, Gen 11: mean=15.3, Gen 12: mean=15.3, Gen 13: mean=15.4
        Changes over last 3: [0.1, 0.0, 0.1]
        max(0.1, 0.0, 0.1) = 0.1 > 0.05 → NOT converged

        Gen 14: mean=15.4, Gen 15: mean=15.4, Gen 16: mean=15.4
        Changes over last 3: [0.0, 0.0, 0.0]
        max(0.0, 0.0, 0.0) = 0.0 < 0.05 → CONVERGED!

    Used by: run_evolution() after each generation
    Related: run_evolution()
    """
    # Need at least window+1 generations to check convergence
    if len(all_stats) < window + 1:
        return False

    # Extract last N+1 mean fitness values
    recent_means = [s['mean_fitness'] for s in all_stats[-(window+1):]]

    # Calculate consecutive differences
    changes = [abs(recent_means[i+1] - recent_means[i]) for i in range(window)]

    # Converged if max change is below threshold
    return max(changes) < threshold


def evolve_generation(
    era: str,
    current_generation: int,
    couchbase_client: CouchbaseClient,
    compression_model: str = "claude",
    population_size: int = 20,
    elite_fraction: float = 0.2,
    mutation_fraction: float = 0.2,
    immigration_fraction: float = 0.08,
    tags_per_mutation: int = 1,
    use_token_metric: bool = False,
    prompt_temperature: float = 1.0,
    single_tag: bool = False
) -> Dict:
    """
    Evolve from generation N to generation N+1.

    This is the main orchestrator of the genetic algorithm. It coordinates
    all GA operators (selection, crossover, mutation, immigration) to create
    the next generation from the current one.

    Process:
    1. Load current generation from database
    2. Select elite (top 20% by fitness)
    3. Create children using GA operators (crossover, mutation, immigration)
    4. Evaluate ONLY children (elite fitness carried forward)
    5. Store next generation to database
    6. Calculate and return statistics

    CRITICAL - Elite Optimization:
    Elite prompts are NOT re-evaluated. They carry their fitness forward
    from the previous generation. This saves evaluation time and is
    scientifically valid because identical prompts with temperature=0
    produce identical results.

    CRITICAL - Immigration Pattern:
    Immigration occurs on ODD generations ONLY (Gen 1, 3, 5, ...).
    Even generations (Gen 0, 2, 4, ...) have NO immigration.
    This allows exploration patterns to stabilize between fresh diversity injections.

    CRITICAL - Error Handling:
    Follows fail-loud philosophy. If child creation fails after 3 retries,
    the entire generation evolution is aborted with a clear error message.
    No silent fallbacks or partial generations.

    Args:
        era: Era identifier (e.g., "test-1", "mixed-1")
        current_generation: Current generation number (e.g., 0 for Gen 0→Gen 1)
        couchbase_client: Connected CouchbaseClient instance
        compression_model: Model for compression ("claude", "openai", "gemini")
        population_size: Total population size (default 20)
        elite_fraction: Fraction to keep as elite (default 0.2 = 20%)
        mutation_fraction: Fraction to create via mutation (default 0.2 = 20%)
        immigration_fraction: Fraction to add as immigrants on ODD gens (default 0.08 = 8%)
        tags_per_mutation: Number of tags to mutate per mutation child (default 1)
        use_token_metric: If True, use token-based compression ratio for fitness

    Returns:
        Statistics dictionary with:
        - Population composition (elite/crossover/mutation/immigrant counts)
        - Fitness metrics (mean/std/median/min/max)
        - Timing information
        - Metadata (era, generation, population_size)

    Raises:
        ValueError: If generation N not found, has invalid data, or parameters invalid
        Exception: If child creation fails after retries

    Example:
        >>> with CouchbaseClient() as cb:
        ...     stats = evolve_generation(
        ...         era="test-1",
        ...         current_generation=0,
        ...         couchbase_client=cb,
        ...         compression_model="claude",
        ...         population_size=20
        ...     )
        >>> stats["population_size"]  # 20
        >>> stats["elite_count"]  # 4
        >>> stats["immigrant_count"]  # 2 (Gen 1 is odd)
        >>> stats["mean_fitness"]  # 13.4

    Used by: Main evolution loop script, testing scripts
    Creates: Next generation population, evolution statistics
    Related: GA operators (selection, mutation, crossover, immigration)
    """
    start_time = time.time()
    next_gen = current_generation + 1

    # -------------------------------------------------------------------------
    # STEP 0: Validate Parameters
    # -------------------------------------------------------------------------
    validate_ga_parameters(
        population_size=population_size,
        elite_fraction=elite_fraction,
        mutation_fraction=mutation_fraction,
        immigration_fraction=immigration_fraction
    )

    print(f"\n{'='*60}")
    print(f"EVOLVING: {era} Gen {current_generation} → Gen {next_gen}")
    print(f"{'='*60}\n")

    # -------------------------------------------------------------------------
    # STEP 1: Load Generation N
    # -------------------------------------------------------------------------
    print(f"[1/6] Loading Generation {current_generation}...")
    prompts = load_generation(couchbase_client, era, current_generation)
    print(f"✓ Loaded {len(prompts)} prompts from Gen {current_generation}")

    # -------------------------------------------------------------------------
    # STEP 2: Select Elite
    # -------------------------------------------------------------------------
    print(f"\n[2/6] Selecting elite ({elite_fraction*100:.0f}% of population)...")
    elite = select_elite(prompts, elite_fraction=elite_fraction)
    elite_count = len(elite)

    print(f"✓ Selected {elite_count} elite prompts")
    print(f"  Top fitness: {elite[0].fitness:.2f}")
    print(f"  Min elite fitness: {elite[-1].fitness:.2f}")

    # -------------------------------------------------------------------------
    # STEP 3: Create Children (with retry logic)
    # -------------------------------------------------------------------------
    # Calculate child counts using percentage-based parameters
    mutation_count = int(population_size * mutation_fraction)

    # Immigration: 8% on ODD generations only (Gen 1, 3, 5, ...)
    # Gen 0 is even, so Gen 1 (next_gen) is odd
    if next_gen % 2 == 0:
        # Even generation - NO immigration
        immigrant_count = 0
    else:
        # Odd generation - HAS immigration (ceil to round up)
        immigrant_count = math.ceil(population_size * immigration_fraction)

    crossover_count = population_size - elite_count - mutation_count - immigrant_count

    # Sanity check
    assert crossover_count >= 0, f"Invalid parameters: crossover_count={crossover_count}"

    print(f"\n[3/6] Creating children...")
    print(f"  Crossover: {crossover_count}")
    print(f"  Mutation: {mutation_count} (mutating {tags_per_mutation} tag(s) each)")
    print(f"  Immigration: {immigrant_count} {'(odd gen)' if next_gen % 2 == 1 else '(even gen - skipped)'}")
    print(f"  Total children: {crossover_count + mutation_count + immigrant_count}")

    all_children = []

    # 3a: Crossover children
    print(f"\n  Creating {crossover_count} crossover children...")
    crossover_children = []
    for i in range(crossover_count):
        for attempt in range(3):
            try:
                p1 = random.choice(elite)
                p2 = random.choice(elite)
                child = crossover(p1, p2, era=era, single_tag=single_tag)
                crossover_children.append(child)
                if (i + 1) % 10 == 0 or (i + 1) == crossover_count:
                    print(f"    [{i+1}/{crossover_count}] created")
                break
            except Exception as e:
                if attempt == 2:
                    raise Exception(f"Crossover {i+1}/{crossover_count} failed after 3 attempts: {e}")
                print(f"    Retry {attempt+1}/3 for crossover {i+1}")
                time.sleep(2 ** attempt)

    all_children.extend(crossover_children)
    print(f"✓ Created {len(crossover_children)} crossover children")

    # 3b: Mutation children
    print(f"\n  Creating {mutation_count} mutation children...")
    mutation_children = []
    for i in range(mutation_count):
        for attempt in range(3):
            try:
                parent = random.choice(elite)
                child = mutate_prompt(parent, mutation_rate=tags_per_mutation, era=era, temperature=prompt_temperature)
                mutation_children.append(child)
                if (i + 1) % 5 == 0 or (i + 1) == mutation_count:
                    print(f"    [{i+1}/{mutation_count}] created")
                break
            except Exception as e:
                if attempt == 2:
                    raise Exception(f"Mutation {i+1}/{mutation_count} failed after 3 attempts: {e}")
                print(f"    Retry {attempt+1}/3 for mutation {i+1}")
                time.sleep(2 ** attempt)

    all_children.extend(mutation_children)
    print(f"✓ Created {len(mutation_children)} mutation children")

    # 3c: Immigrants (only on odd generations)
    immigrants = []
    if immigrant_count > 0:
        print(f"\n  Creating {immigrant_count} immigrants...")
        for i in range(immigrant_count):
            for attempt in range(3):
                try:
                    chunk = get_random_suitable_chunk(couchbase_client)
                    immigrant = create_immigrant(
                        era=era,
                        generation=next_gen,
                        paragraph_text=chunk["text"],
                        paragraph_id=chunk["chunk_id"],
                        temperature=prompt_temperature
                    )
                    immigrants.append(immigrant)
                    print(f"    [{i+1}/{immigrant_count}] created")
                    break
                except Exception as e:
                    if attempt == 2:
                        raise Exception(f"Immigrant {i+1}/{immigrant_count} failed after 3 attempts: {e}")
                    print(f"    Retry {attempt+1}/3 for immigrant {i+1}")
                    time.sleep(2 ** attempt)

        all_children.extend(immigrants)
        print(f"✓ Created {len(immigrants)} immigrants")
    else:
        print(f"\n  No immigration (even generation - Gen {next_gen})")

    # -------------------------------------------------------------------------
    # STEP 4: Select Evaluation Corpus (Vetted Pool)
    # -------------------------------------------------------------------------
    print(f"\n[4/7] Selecting evaluation corpus...")

    from src.corpus_sampler import select_evaluation_corpus

    evaluation_corpus = select_evaluation_corpus(
        couchbase_client=couchbase_client,
        corpus_size=20,
        min_words=550,
        max_words=650
    )
    corpus_ids = [p["chunk_id"] for p in evaluation_corpus]
    print(f"✓ Selected {len(evaluation_corpus)} vetted paragraphs for evaluation pool")

    # -------------------------------------------------------------------------
    # STEP 5: Evaluate Children Only (elite fitness carries forward)
    # -------------------------------------------------------------------------
    print(f"\n[5/7] Evaluating {len(all_children)} children...")
    print(f"  (Elite fitness carried forward - saves ~{elite_count * 8} seconds!)")
    print(f"  Each child randomly selects from vetted pool of {len(evaluation_corpus)} paragraphs")

    for idx, child in enumerate(all_children):
        print(f"\n  [{idx+1}/{len(all_children)}] Evaluating {child.type} {child.prompt_id[:8]}...")

        # Randomly select ONE paragraph from vetted pool
        para = random.choice(evaluation_corpus)

        # Evaluate
        results = evaluate_prompt_fitness(
            prompt_object=child,
            paragraph_text=para["text"],
            compression_model=compression_model,
            judge_models=["openai", "claude", "gemini"],
            use_token_metric=use_token_metric
        )

        # Update child with results
        child.fitness = results["fitness"]
        child.original_text = results["original_text"]
        child.compressed_text = results["compressed_text"]
        child.original_words = results["original_words"]
        child.compressed_words = results["compressed_words"]
        child.compression_ratio = results["compression_ratio"]
        child.original_tokens = results["original_tokens"]
        child.compressed_tokens = results["compressed_tokens"]
        child.token_compression_ratio = results["token_compression_ratio"]
        child.quality_scores = results["quality_scores"]
        child.quality_score_avg = results["quality_score_avg"]
        child.survival_factor = results["survival_factor"]

        print(f"    Fitness: {child.fitness:.4f} (ratio: {child.compression_ratio:.2f}, quality: {child.quality_score_avg:.2f})")

    print(f"\n✓ Evaluated {len(all_children)} children")

    # -------------------------------------------------------------------------
    # STEP 6: Store Generation N+1
    # -------------------------------------------------------------------------
    print(f"\n[6/7] Storing Generation {next_gen}...")

    # Update elite metadata (they carry forward to N+1 with lineage tracking)
    for elite_prompt in elite:
        # Set parent to reference this same prompt_id in previous generation
        # Enables recursive tree traversal: Gen N+1 -> Gen N -> ... -> Gen 0
        elite_prompt.parents = [elite_prompt.prompt_id]
        elite_prompt.generation = next_gen
        # Mark as elite type for visualization
        elite_prompt.type = "elite"

    # Combine all prompts
    next_generation = elite + all_children

    print(f"  Total population: {len(next_generation)} prompts")
    print(f"    Elite (carried forward): {elite_count}")
    print(f"    Children (evaluated): {len(all_children)}")

    # Store to database with era-gen-id format
    for idx, prompt in enumerate(next_generation):
        doc_id = f"{prompt.era}-gen-{prompt.generation}-{prompt.prompt_id}"
        couchbase_client.save_document("generations", doc_id, prompt.to_dict())
        if (idx + 1) % 20 == 0 or (idx + 1) == len(next_generation):
            print(f"    Saved {idx+1}/{len(next_generation)} prompts")

    print(f"✓ Stored {len(next_generation)} prompts to Gen {next_gen}")

    # -------------------------------------------------------------------------
    # STEP 7: Calculate Statistics
    # -------------------------------------------------------------------------
    print(f"\n[7/7] Calculating generation statistics...")

    elapsed_time = time.time() - start_time

    fitness_metric = "tokens" if use_token_metric else "words"

    stats = calculate_generation_stats(
        prompts=next_generation,
        era=era,
        generation=next_gen,
        elite_count=elite_count,
        crossover_count=len(crossover_children),
        mutation_count=len(mutation_children),
        immigrant_count=len(immigrants),
        evaluated_count=len(all_children),
        elapsed_seconds=elapsed_time,
        evaluation_corpus_ids=corpus_ids,
        fitness_metric=fitness_metric,
        compression_model=compression_model,
        prompt_temperature=prompt_temperature,
        single_tag=single_tag
    )

    print(f"\n✓ Generation {next_gen} complete!")
    print(f"\n{'='*60}")
    print(f"STATISTICS - {era} Gen {next_gen}")
    print(f"{'='*60}")
    print(f"Population: {stats['population_size']}")
    print(f"  Elite: {stats['elite_count']}")
    print(f"  Crossover: {stats['crossover_count']}")
    print(f"  Mutation: {stats['mutation_count']}")
    print(f"  Immigrants: {stats['immigrant_count']}")
    print(f"  Evaluated: {stats['evaluated_count']}")
    print(f"\nFitness:")
    print(f"  Mean: {stats['mean_fitness']:.2f}")
    print(f"  Std: {stats['std_fitness']:.2f}")
    print(f"  Median: {stats['median_fitness']:.2f}")
    print(f"  Range: [{stats['min_fitness']:.2f}, {stats['max_fitness']:.2f}]")
    print(f"\nTime: {stats['elapsed_seconds']:.1f} seconds ({stats['elapsed_seconds']/60:.1f} minutes)")
    print(f"{'='*60}\n")

    return stats


def run_evolution(
    era: str,
    starting_generation: int,
    num_generations: int,
    couchbase_client: CouchbaseClient,
    compression_model: str = "claude",
    population_size: int = 20,
    elite_fraction: float = 0.2,
    mutation_fraction: float = 0.2,
    immigration_fraction: float = 0.08,
    tags_per_mutation: int = 1,
    convergence_window: int = 3,
    convergence_threshold: float = 0.05,
    check_convergence: bool = True,
    use_token_metric: bool = False,
    prompt_temperature: float = 1.0,
    single_tag: bool = False
) -> List[Dict]:
    """
    Orchestrate multi-generation evolution experiment (Gen 0 → Gen N).

    This is the top-level function for running complete genetic algorithm
    experiments. It loops over generations, coordinating all GA operators
    (selection, mutation, crossover, immigration) through the evolve_generation()
    function.

    Process:
    1. Print experiment header with parameters
    2. Loop from starting_generation to starting_generation + num_generations
    3. For each generation:
       - Evolve Gen N → Gen N+1 using evolve_generation()
       - Store statistics to 'generations' collection
       - Check for convergence (fitness plateau)
       - Stop early if converged
    4. Print experiment summary
    5. Return all generation statistics for analysis

    Convergence Detection:
    The function monitors mean fitness over a sliding window. If the maximum
    change in mean fitness over the last `convergence_window` generations is
    less than `convergence_threshold`, evolution stops early (unless
    check_convergence=False).

    Why convergence matters:
    - Saves time (don't run unnecessary generations)
    - Saves API costs (~$4-8 per generation)
    - Scientifically valid stopping criterion
    - Indicates fitness plateau reached

    Resume Capability:
    The function supports resuming experiments from any generation. Simply
    set starting_generation=N to pick up where you left off. All data is
    preserved in the database.

    Error Handling (Fail-Loud):
    If any generation fails after retries, the entire experiment aborts with
    a clear error message showing how to resume. No partial generations or
    silent fallbacks.

    Args:
        era: Era identifier (e.g., "test-1", "mixed-1")
        starting_generation: Generation to start from (usually 0 for new experiments)
        num_generations: Maximum generations to evolve (may stop early if converged)
        couchbase_client: Connected CouchbaseClient instance
        compression_model: Model for compression ("claude", "openai", "gemini")
        population_size: Total population size (default 20)
        elite_fraction: Fraction to keep as elite (default 0.2 = 20%)
        mutation_fraction: Fraction to create via mutation (default 0.2 = 20%)
        immigration_fraction: Fraction to add as immigrants on ODD gens (default 0.08 = 8%)
        tags_per_mutation: Number of tags to mutate per mutation child (default 1)
        convergence_window: Generations to check for plateau (default 3)
        convergence_threshold: Max mean fitness change for convergence (default 0.05)
        check_convergence: Whether to stop on convergence detection (default True).
                          Set to False to continue running despite fitness plateaus.

    Returns:
        List of statistics dictionaries, one per generation evolved.
        Each dict contains:
        - Population composition (elite/crossover/mutation/immigrant counts)
        - Fitness metrics (mean/std/median/min/max)
        - Timing information
        - Metadata (era, generation, population_size)

    Raises:
        ValueError: If starting generation not found in database
        Exception: If any generation fails after retries (fail-loud)

    Example:
        >>> with CouchbaseClient() as cb:
        ...     # Run full 20-generation experiment
        ...     stats = run_evolution(
        ...         era="mixed-1",
        ...         starting_generation=0,
        ...         num_generations=20,
        ...         couchbase_client=cb
        ...     )
        >>> len(stats)  # 12 (stopped early at convergence)
        >>> stats[0]["generation"]  # 1
        >>> stats[-1]["generation"]  # 12
        >>> stats[-1]["mean_fitness"]  # 15.4

        >>> # Resume from generation 12
        >>> more_stats = run_evolution(
        ...     era="mixed-1",
        ...     starting_generation=12,
        ...     num_generations=8,
        ...     couchbase_client=cb,
        ...     mutation_rate=2  # Increased to escape local optimum
        ... )

    Used by: Main evolution scripts, experimental workflows
    Creates: Complete generation lineage, statistics for Paper 1 & 2
    Related: evolve_generation() (single-generation evolution)
             store_generation_stats() (database storage)
             has_converged() (convergence detection)
    """
    experiment_start_time = time.time()

    # Print experiment header
    print("\n" + "="*70)
    print(f"EVOLUTION EXPERIMENT: {era}")
    print("="*70)
    print(f"Starting Generation: {starting_generation}")
    print(f"Target Generations: {num_generations} (max, may stop early if converged)")
    print(f"Population: {population_size}")
    print(f"Compression Model: {compression_model}")
    print(f"Elite Fraction: {elite_fraction * 100:.0f}%")
    print(f"Mutation Fraction: {mutation_fraction * 100:.0f}% ({tags_per_mutation} tag(s) per prompt)")
    print(f"Immigration: {immigration_fraction * 100:.0f}% (odd generations only)")
    print(f"Convergence: window={convergence_window}, threshold={convergence_threshold}, "
          f"stop_on_convergence={check_convergence}")
    print("="*70 + "\n")

    all_stats = []

    # Main evolution loop
    for gen in range(starting_generation, starting_generation + num_generations):
        try:
            # Evolve one generation
            print(f"\n{'─'*70}")
            print(f"Generation {gen} → {gen+1}")
            print(f"{'─'*70}")

            stats = evolve_generation(
                era=era,
                current_generation=gen,
                couchbase_client=couchbase_client,
                compression_model=compression_model,
                population_size=population_size,
                elite_fraction=elite_fraction,
                mutation_fraction=mutation_fraction,
                immigration_fraction=immigration_fraction,
                tags_per_mutation=tags_per_mutation,
                use_token_metric=use_token_metric,
                prompt_temperature=prompt_temperature,
                single_tag=single_tag
            )

            # Load current and previous generation prompts for statistical testing
            current_gen_prompts = load_generation(couchbase_client, era, gen + 1)
            previous_gen_prompts = load_generation(couchbase_client, era, gen) if gen >= 0 else None

            # Store statistics to database with statistical tests
            store_generation_stats(
                era,
                gen + 1,
                stats,
                couchbase_client,
                current_generation_prompts=current_gen_prompts,
                previous_generation_prompts=previous_gen_prompts
            )

            # Collect for return value
            all_stats.append(stats)

            # Print generation summary
            print(f"\n✅ Gen {gen} → Gen {gen+1} complete: "
                  f"mean_fitness={stats['mean_fitness']:.2f}, "
                  f"time={stats['elapsed_seconds']/60:.1f}min")

            # Check convergence (can be disabled via check_convergence=False)
            if has_converged(all_stats, convergence_window, convergence_threshold):
                if check_convergence:
                    print(f"\n{'='*70}")
                    print("🎯 CONVERGENCE DETECTED - STOPPING EVOLUTION")
                    print(f"{'='*70}")
                    print(f"Fitness plateau reached after {len(all_stats)} generations")
                    print(f"Final mean fitness: {stats['mean_fitness']:.2f}")
                    print(f"Max fitness change over last {convergence_window} gens: "
                          f"<{convergence_threshold}")
                    print("="*70)
                    break
                else:
                    # Still notify but don't stop
                    print(f"\n⚠️ CONVERGENCE DETECTED (continuing due to --no-convergence-stop)")

        except Exception as e:
            print(f"\n{'='*70}")
            print("❌ FATAL ERROR")
            print(f"{'='*70}")
            print(f"Generation {gen}→{gen+1} failed: {e}")
            print(f"\nLast successful generation: {gen}")
            print(f"Generations completed: {len(all_stats)}")
            print(f"\nTo resume this experiment:")
            print(f"  run_evolution(")
            print(f"      era='{era}',")
            print(f"      starting_generation={gen},")
            print(f"      num_generations={num_generations - len(all_stats)},")
            print(f"      couchbase_client=cb")
            print(f"  )")
            print("="*70 + "\n")
            raise  # Re-raise to stop execution (fail-loud)

    # Calculate experiment totals
    experiment_elapsed = time.time() - experiment_start_time
    total_evals = sum(s['evaluated_count'] for s in all_stats)
    final_gen = starting_generation + len(all_stats)

    # Print experiment summary
    print(f"\n{'='*70}")
    print("📊 EVOLUTION COMPLETE")
    print(f"{'='*70}")
    print(f"Era: {era}")
    print(f"Generations Evolved: {len(all_stats)} "
          f"({'converged early' if len(all_stats) < num_generations else 'completed target'})")
    print(f"Final Generation: {final_gen}")
    print(f"Final Mean Fitness: {all_stats[-1]['mean_fitness']:.2f}")
    print(f"Total Time: {experiment_elapsed/3600:.2f} hours ({experiment_elapsed/60:.1f} minutes)")
    print(f"Total Evaluations: {total_evals}")
    print(f"\n💰 Estimated API Calls:")
    print(f"  Prompt generation: ~{total_evals}")
    print(f"  Compressions: {total_evals}")
    print(f"  Judgments: {total_evals * 3} (3 models)")
    print(f"  Total: ~{total_evals * 5} API calls")
    print("="*70 + "\n")

    return all_stats
