"""
Genetic algorithm operators for prompt evolution.

This module implements the four core GA operators:
1. Selection: Identify elite performers (top 20% by fitness)
2. Mutation: Modify tags to explore variations (Phase 6)
3. Crossover: Combine tags from two parents (Phase 7)
4. Immigration: Inject new prompts for diversity (Phase 8)

These operators work together to evolve prompts toward higher fitness:
- Selection provides survival pressure
- Mutation enables local search and refinement
- Crossover recombines successful patterns
- Immigration prevents premature convergence

Used by: Evolution orchestrator, testing scripts
Creates: Next generation populations with improved fitness
Critical for: Evolution gradient, lineage tracking, phylogenetic analysis

Related files:
- src/models.py: Prompt and PromptTag structures
- src/fitness_evaluator.py: Fitness calculation
- src/initial_prompts.py: Generation 0 creation
- src/llm_clients.py: LLM API wrappers for mutation
"""

from typing import List
import random
import json
import time
from uuid import uuid4
from src.models import Prompt, PromptTag
from src.llm_clients import generate_with_random_model


# Custom exceptions for fail-loud error handling
class MutationFailureError(Exception):
    """Raised when LLM fails to generate valid mutation after retries."""
    pass


class JSONParseError(Exception):
    """Raised when LLM response cannot be parsed as JSON."""
    pass


def select_elite(
    prompts: List[Prompt],
    elite_fraction: float = 0.2
) -> List[Prompt]:
    """
    Select top performers by fitness for breeding.

    This is the selection mechanism for the genetic algorithm. The elite
    (top N% by fitness) automatically survive to the next generation and
    serve as the parent pool for mutation and crossover operations.

    Selection pressure drives evolution toward higher fitness scores.
    The default 20% elite fraction balances exploration (diverse gene pool)
    with exploitation (focusing on successful patterns).

    Args:
        prompts: Population with fitness scores (List[Prompt])
        elite_fraction: Fraction to keep (default 0.2 = top 20%)

    Returns:
        Elite subset, sorted by fitness descending (highest first)

    Edge Cases:
        - Empty population → return empty list
        - elite_count < 1 → return at least 1 prompt if population exists
        - All fitness = 0 → still return top N by sort stability
        - None fitness values → sort to end (treated as lowest)

    Example:
        >>> population = [p1, p2, ..., p100]  # 100 prompts
        >>> elite = select_elite(population, elite_fraction=0.2)
        >>> len(elite)  # 20 prompts
        >>> elite[0].fitness >= elite[-1].fitness  # True (sorted)

    Used by: Evolution orchestrator (Phase 9)
    Creates: Parent pool for mutation/crossover, survivors to next generation
    Related: mutation_prompt(), crossover(), evolve_population()
    """
    # Step 1: Handle empty population
    if not prompts:
        return []

    # Step 2: Sort by fitness (descending)
    # Use key function that handles None fitness values
    sorted_prompts = sorted(
        prompts,
        key=lambda p: p.fitness if p.fitness is not None else -1,
        reverse=True
    )

    # Step 3: Calculate elite count
    elite_count = int(len(prompts) * elite_fraction)

    # Step 4: Ensure at least 1 elite if population exists
    if elite_count < 1 and len(prompts) > 0:
        elite_count = 1

    # Step 5: Return top N
    return sorted_prompts[:elite_count]


def parse_llm_json(response: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code blocks.

    LLMs sometimes wrap JSON in markdown code fences. This function
    strips those fences but still requires valid JSON - it does NOT
    fallback to guessing or extracting.

    Args:
        response: Raw LLM response text

    Returns:
        Parsed JSON as dictionary

    Raises:
        JSONParseError: If response cannot be parsed as valid JSON

    Example:
        >>> parse_llm_json('{"key": "value"}')
        {'key': 'value'}
        >>> parse_llm_json('```json\\n{"key": "value"}\\n```')
        {'key': 'value'}
        >>> parse_llm_json('invalid json')
        JSONParseError: Cannot parse as JSON: invalid json
    """
    # Remove markdown code fences if present
    cleaned = response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]  # Remove ```json
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]   # Remove ```

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]  # Remove trailing ```

    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as e:
        raise JSONParseError(f"Cannot parse as JSON: {response[:200]}...") from e


def mutate_prompt(
    parent: Prompt,
    mutation_rate: int = 1,
    era: str = None,
    temperature: float = 1.0
) -> Prompt:
    """
    Create child prompt by mutating parent tags.

    Takes a parent prompt and improves mutation_rate number of tags through
    LLM-guided refinement. The child inherits unmutated tags directly (same guid)
    while mutated tags get new guids and track their parent via parent_tag_guid.

    This operator enables local search around successful prompts, gradually
    improving performance through incremental refinements. It's the primary
    mechanism for exploitation in the genetic algorithm.

    CRITICAL - Lineage Tracking:
    - Mutated tags: NEW guid, parent_tag_guid=parent's guid, source="mutation"
    - Unmutated tags: SAME guid, SAME parent_tag_guid, SAME source (inherited)
    - Prompt: type="mutation", parents=[parent.prompt_id], generation=parent+1

    CRITICAL - Error Handling:
    - Fails loud if LLM cannot generate valid mutation (no silent fallbacks)
    - Retries up to 3 times with exponential backoff
    - Raises MutationFailureError if all retries exhausted
    - This maintains scientific validity and research reproducibility

    Args:
        parent: Parent prompt to mutate (must have all 5 tags)
        mutation_rate: Number of tags to mutate (default 1, can increase to 2)
        era: Era identifier (defaults to parent.era if None)

    Returns:
        Child Prompt with:
        - mutation_rate tags mutated (new guid, improved text)
        - (5 - mutation_rate) tags inherited (same guid, same text)
        - fitness=None (unevaluated, will be evaluated separately)
        - proper lineage tracking

    Raises:
        ValueError: If parent missing tags or mutation_rate > 5
        MutationFailureError: If LLM fails to generate valid mutation after retries
        JSONParseError: If LLM response cannot be parsed

    Example:
        >>> parent = elite_prompts[0]  # High fitness prompt
        >>> child = mutate_prompt(parent, mutation_rate=1, era="mixed-1")
        >>> child.generation  # parent.generation + 1
        >>> child.type  # "mutation"
        >>> child.parents  # [parent.prompt_id]
        >>> # 1 tag has new guid, 4 tags have parent guids

    Used by: Evolution orchestrator (Phase 9)
    Creates: Child prompts for next generation
    Related: select_elite(), crossover(), evolve_population()
    """
    MAX_RETRIES = 3
    TAG_NAMES = ["role", "compression_target", "fidelity", "constraints", "output"]

    # Step 1: Validate input
    for tag_name in TAG_NAMES:
        tag = getattr(parent, tag_name)
        if tag is None or not tag.text:
            raise ValueError(f"Parent missing or empty {tag_name} tag")

    if mutation_rate < 1 or mutation_rate > 5:
        raise ValueError(f"mutation_rate must be 1-5, got {mutation_rate}")

    # Default era to parent's era
    if era is None:
        era = parent.era

    # Step 2: Select tags to mutate (randomly)
    tags_to_mutate = random.sample(TAG_NAMES, mutation_rate)

    # Step 3: Mutate selected tags with retry logic
    mutated_tags = {}
    model_used = None

    for tag_name in tags_to_mutate:
        parent_tag = getattr(parent, tag_name)

        # Build mutation prompt
        mutation_prompt = f"""You are improving a semantic compression prompt tag.

TAG TYPE: {tag_name}
CURRENT TAG: {parent_tag.text}

CONTEXT:
- GOAL: Achieve maximum compression while preserving core semantic content
- OPTIMIZATION TARGET: Minimize token count (not word count)
- USE CASE: Output will be used in retrieval systems, not human reading

TASK: Improve this tag to make compression more effective.

Guidelines:
- Be more specific and actionable
- Add measurable criteria where possible
- Keep the same general purpose
- Make it 1-3 sentences
- Focus on improving compression quality and efficiency

IMPORTANT CONSTRAINTS:
- DO NOT add hard word limits (e.g., "output exactly 45 words")
- DO NOT add hard sentence limits (e.g., "use maximum 3 sentences")
- DO NOT add hard token limits (e.g., "compress to 100 tokens")
- Focus on semantic compression STRATEGIES, not numeric targets

RESPOND WITH ONLY JSON (no markdown, no explanation):
{{
  "improved_tag": "your improved tag text here"
}}"""

        # Retry loop with exponential backoff
        improved_text = None
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                # Call LLM with random model selection (temperature=1.0 for creativity)
                response, model_name = generate_with_random_model(mutation_prompt, temperature=temperature)

                # Track which model did the mutation (only save once)
                if model_used is None:
                    model_used = model_name

                # Parse JSON response (strict parsing, no fallbacks)
                data = parse_llm_json(response)
                improved_text = data.get("improved_tag", "").strip()

                # Validate improvement actually happened
                if not improved_text:
                    raise MutationFailureError(f"LLM returned empty improved_tag for '{tag_name}'")

                if improved_text == parent_tag.text.strip():
                    raise MutationFailureError(f"LLM returned identical text for '{tag_name}'")

                # Success! Break out of retry loop
                break

            except (JSONParseError, MutationFailureError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    # Exponential backoff before retry
                    time.sleep(2 ** attempt)
                    continue
                else:
                    # All retries exhausted - FAIL LOUD
                    raise MutationFailureError(
                        f"Failed to mutate tag '{tag_name}' after {MAX_RETRIES} attempts. "
                        f"Last error: {e}. Parent text: {parent_tag.text[:100]}..."
                    ) from e

        # Create mutated tag with NEW guid
        mutated_tags[tag_name] = PromptTag(
            guid=str(uuid4()),  # NEW guid
            text=improved_text,
            parent_tag_guid=parent_tag.guid,  # Link to parent
            source="mutation",
            origin="mutation"  # This tag originated from mutation
        )

    # Step 4: Copy unmutated tags (INHERIT guids)
    child_tags = {}

    for tag_name in TAG_NAMES:
        if tag_name in mutated_tags:
            # Use the mutated version
            child_tags[tag_name] = mutated_tags[tag_name]
        else:
            # Inherit parent tag unchanged - SAME guid flows through crossover-style
            parent_tag = getattr(parent, tag_name)
            child_tags[tag_name] = PromptTag(
                guid=parent_tag.guid,  # SAME guid as parent (flows through)
                text=parent_tag.text,  # SAME text
                parent_tag_guid=parent_tag.guid,  # Points to immediate parent (same guid in previous gen)
                source="crossover",  # This is inheritance, not mutation
                origin=parent_tag.origin  # PRESERVE origin (how tag was first created)
            )

    # Step 5: Create child prompt
    child = Prompt(
        prompt_id=str(uuid4()),
        generation=parent.generation + 1,
        era=era,
        type="mutation",
        parents=[parent.prompt_id],
        model_used=model_used,  # Which model did the mutation
        source_paragraph_id=parent.source_paragraph_id,  # Same test paragraph
        role=child_tags["role"],
        compression_target=child_tags["compression_target"],
        fidelity=child_tags["fidelity"],
        constraints=child_tags["constraints"],
        output=child_tags["output"],
        # Evaluation fields remain None (unevaluated)
        fitness=None,
        original_text=None,
        compressed_text=None,
        original_words=None,
        compressed_words=None,
        compression_ratio=None,
        quality_scores=None,
        quality_score_avg=None,
        survival_factor=None
    )

    return child


def crossover(
    parent1: Prompt,
    parent2: Prompt,
    era: str = None,
    single_tag: bool = False
) -> Prompt:
    """
    Create child prompt by crossing over two parent prompts.

    Takes two parent prompts and creates one child by randomly selecting each
    of the 5 tags from either parent1 or parent2. Tags are inherited with their
    existing guids, maintaining the phylogenetic chain. Only the source field
    is updated to "crossover" to mark this recombination event.

    This operator enables exploration of the fitness landscape by combining
    successful tag patterns from different high-performing parents. Unlike
    mutation (which creates new variations), crossover recombines existing
    successful patterns.

    CRITICAL - Lineage Tracking (DIFFERENT from mutation):
    - ALL tags: guid INHERITED from source parent (NOT new guid)
    - ALL tags: text INHERITED from source parent
    - ALL tags: parent_tag_guid INHERITED from source parent
    - ALL tags: source set to "crossover" (CHANGED from parent's source)
    - Prompt: type="crossover", parents=[parent1.id, parent2.id], generation=max+1

    This inheritance pattern enables phylogenetic analysis to:
    - Track which tags came from which evolutionary lineages
    - Identify successful tag combinations across generations
    - Distinguish inherited tags (same guid) from mutated tags (new guid)

    CRITICAL - Error Handling (Fail Loud Philosophy):
    - Raises ValueError if parents missing required tags
    - Raises ValueError if parents from different eras
    - NO silent fallbacks or default values
    - Note: Era mismatch should never happen in production (parents selected
      from same generation+era), but we validate defensively

    Args:
        parent1: First parent prompt (must have all 5 tags)
        parent2: Second parent prompt (must have all 5 tags)
        era: Era identifier (defaults to parent1.era, must match parent2.era)

    Returns:
        Child Prompt with:
        - Each of 5 tags randomly selected from parent1 or parent2
        - All tags have inherited guids (not new guids)
        - All tags have source="crossover"
        - fitness=None (unevaluated, will be evaluated separately)
        - proper lineage tracking (2 parents, generation=max+1)

    Raises:
        ValueError: If parents missing tags, from different eras, or invalid era

    Example:
        >>> elite = select_elite(population, elite_fraction=0.2)
        >>> parent1, parent2 = elite[0], elite[1]  # Top 2 performers
        >>> child = crossover(parent1, parent2, era="mixed-1")
        >>> child.generation  # max(parent1.generation, parent2.generation) + 1
        >>> child.type  # "crossover"
        >>> child.parents  # [parent1.prompt_id, parent2.prompt_id]
        >>> child.role.source  # "crossover"
        >>> # Child's role.guid matches either parent1.role.guid or parent2.role.guid

    Used by: Evolution orchestrator (Phase 9)
    Creates: Child prompts for next generation (majority of population)
    Related: select_elite(), mutate_prompt(), evolve_population()
    """
    TAG_NAMES = ["role", "compression_target", "fidelity", "constraints", "output"]

    # Step 1: Validate inputs (fail loud)
    for tag_name in TAG_NAMES:
        tag = getattr(parent1, tag_name)
        if tag is None or not tag.text:
            raise ValueError(f"Parent1 missing or empty {tag_name} tag")

    for tag_name in TAG_NAMES:
        tag = getattr(parent2, tag_name)
        if tag is None or not tag.text:
            raise ValueError(f"Parent2 missing or empty {tag_name} tag")

    # Determine and validate era
    if era is None:
        era = parent1.era

    # Parents must be from same era (should never happen in production)
    if parent1.era != parent2.era:
        raise ValueError(
            f"Parents from different eras: parent1={parent1.era}, parent2={parent2.era}. "
            f"Crossover requires parents from same evolutionary context."
        )

    if era != parent1.era:
        raise ValueError(
            f"Specified era '{era}' doesn't match parents' era '{parent1.era}'"
        )

    # Step 2: Select source parent for each tag
    child_tags = {}

    if single_tag:
        # SINGLE-TAG MODE: Inherit all from parent1, replace exactly 1 from parent2
        # This enables clearer phylogenetic attribution for Paper 2 analysis
        tag_to_swap = random.choice(TAG_NAMES)

        for tag_name in TAG_NAMES:
            if tag_name == tag_to_swap:
                source_parent = parent2
            else:
                source_parent = parent1

            source_tag = getattr(source_parent, tag_name)
            child_tags[tag_name] = PromptTag(
                guid=source_tag.guid,
                text=source_tag.text,
                parent_tag_guid=source_tag.guid,
                source="crossover",
                origin=source_tag.origin
            )
    else:
        # STANDARD MODE: Random selection per tag (existing behavior)
        for tag_name in TAG_NAMES:
            # Flip a coin: parent1 or parent2?
            source_parent = random.choice([parent1, parent2])
            source_tag = getattr(source_parent, tag_name)

            # Inherit guid, text, origin - change source to "crossover", self-reference parent_tag_guid
            child_tags[tag_name] = PromptTag(
                guid=source_tag.guid,              # INHERITED (not new!)
                text=source_tag.text,              # INHERITED
                parent_tag_guid=source_tag.guid,   # SELF-REFERENCE for graph traversal
                source="crossover",                # CHANGED (operator that brought tag here)
                origin=source_tag.origin           # PRESERVED (how tag was first created)
            )

    # Step 3: Calculate child generation (max of parents + 1)
    child_generation = max(parent1.generation, parent2.generation) + 1

    # Step 4: Create child prompt
    child = Prompt(
        prompt_id=str(uuid4()),
        generation=child_generation,
        era=era,
        type="crossover",
        parents=[parent1.prompt_id, parent2.prompt_id],
        model_used="crossover",  # Not an LLM, but marks the operator
        source_paragraph_id=parent1.source_paragraph_id,  # Inherit from parent1
        role=child_tags["role"],
        compression_target=child_tags["compression_target"],
        fidelity=child_tags["fidelity"],
        constraints=child_tags["constraints"],
        output=child_tags["output"],
        # Evaluation fields remain None (unevaluated)
        fitness=None,
        original_text=None,
        compressed_text=None,
        original_words=None,
        compressed_words=None,
        compression_ratio=None,
        quality_scores=None,
        quality_score_avg=None,
        survival_factor=None
    )

    return child


def create_immigrant(
    era: str,
    generation: int,
    paragraph_text: str,
    paragraph_id: str,
    temperature: float = 1.0
) -> Prompt:
    """
    Create fresh immigrant prompt with no evolutionary history.

    Immigration injects completely new prompts during evolution to prevent
    premature convergence and maintain genetic diversity. Unlike mutation
    (which refines existing prompts) or crossover (which recombines existing
    patterns), immigration generates entirely fresh genetic material.

    This is nearly identical to Generation 0 creation (see initial_prompts.py)
    but marks prompts as "immigrant" type for lineage tracking and phylogenetic
    analysis. Immigrants have no parents and start a new evolutionary lineage.

    CRITICAL - Lineage Tracking:
    - ALL tags: NEW guids (not related to any existing prompts)
    - ALL tags: parent_tag_guid=None (no evolutionary history)
    - ALL tags: source="immigrant" (NOT "initial")
    - Prompt: type="immigrant", parents=None, generation=current_generation

    CRITICAL - Error Handling (Fail Loud):
    - Raises exception if LLM API call fails (no retries, no fallbacks)
    - Raises JSONParseError if response cannot be parsed
    - Raises ValueError if LLM returns empty tag text
    - NO silent fallbacks (unlike Generation 0 which has defaults)
    - Let failures propagate to orchestrator for handling

    Process:
    1. Build LLM generation prompt (same as Generation 0)
    2. Call generate_with_random_model() for model diversity
    3. Parse JSON response (strict parsing, fail if invalid)
    4. Validate all 5 tags present and non-empty
    5. Create Prompt with type="immigrant", generation=N

    Args:
        era: Era identifier (e.g., "test-1", "mixed-1")
        generation: Current generation number (e.g., 5, 10, 15)
        paragraph_text: NOT USED in generation (only stored for evaluation later)
        paragraph_id: Source paragraph ID for tracking

    Returns:
        Unevaluated Prompt with:
        - type="immigrant"
        - generation=current_generation (NOT 0)
        - parents=None
        - All tags: source="immigrant", parent_tag_guid=None
        - fitness=None (will be evaluated separately)

    Raises:
        Exception: If LLM API call fails (fail loud, no fallback)
        JSONParseError: If response cannot be parsed as valid JSON
        ValueError: If LLM returns empty or invalid tag text

    Example:
        >>> # During evolution at generation 5
        >>> with CouchbaseClient() as cb:
        ...     para = get_random_paragraph(cb)
        ...     immigrant = create_immigrant(
        ...         era="mixed-1",
        ...         generation=5,
        ...         paragraph_text=para["text"],
        ...         paragraph_id=para["paragraph_id"]
        ...     )
        >>> immigrant.generation  # 5 (current generation)
        >>> immigrant.type  # "immigrant"
        >>> immigrant.parents  # None
        >>> immigrant.role.source  # "immigrant"
        >>> immigrant.role.parent_tag_guid  # None

    Used by: Evolution orchestrator (Phase 9)
    Creates: Fresh genetic material to prevent local optima
    Related: generate_initial_prompt(), mutate_prompt(), crossover()
    """
    # Step 1: Build LLM generation prompt (no context - trust the LLM)
    generation_prompt = """Generate a semantic compression prompt with 5 sections.

GOAL: Achieve maximum compression while preserving core semantic content
OPTIMIZATION TARGET: Minimize token count (not word count)
USE CASE: Output will be used in retrieval systems, not human reading

Create these 5 sections:
1. ROLE: Establish expertise and task
2. COMPRESSION_TARGET: Specify compression strategy (NOT hard limits)
3. FIDELITY: What must be preserved (concepts, entities, relationships)
4. CONSTRAINTS: What to avoid (explanations, meta-commentary, filler)
5. OUTPUT: Format and style requirements

IMPORTANT CONSTRAINTS:
- DO NOT add hard word limits (e.g., "output exactly 45 words")
- DO NOT add hard sentence limits (e.g., "use maximum 3 sentences")
- DO NOT add hard token limits (e.g., "compress to 100 tokens")
- Focus on semantic compression STRATEGIES, not numeric targets

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "role": "...",
  "compression_target": "...",
  "fidelity": "...",
  "constraints": "...",
  "output": "..."
}"""

    # Step 2: Call random LLM (fail loud if API error)
    response, model_used = generate_with_random_model(
        generation_prompt,
        temperature=temperature  # User-configurable temperature
    )

    # Step 3: Parse JSON response (strict parsing, fail if invalid)
    try:
        tags_dict = parse_llm_json(response)
    except JSONParseError as e:
        # FAIL LOUD - do NOT use fallback defaults
        raise JSONParseError(
            f"Failed to parse immigrant tags from {model_used}. "
            f"Response: {response[:200]}..."
        ) from e

    # Step 4: Validate all required keys present and non-empty
    required_keys = ["role", "compression_target", "fidelity", "constraints", "output"]
    for key in required_keys:
        if key not in tags_dict or not tags_dict[key].strip():
            raise ValueError(
                f"LLM returned empty or missing '{key}' tag. "
                f"Model: {model_used}, Response: {response[:200]}..."
            )

    # Step 5: Create Prompt with "immigrant" lineage tracking
    return Prompt(
        prompt_id=str(uuid4()),
        generation=generation,  # CRITICAL: Use passed parameter, NOT 0
        era=era,
        type="immigrant",       # NOT "initial"
        parents=None,           # No parents
        model_used=model_used,  # Which LLM generated it
        source_paragraph_id=paragraph_id,

        # Create 5 tags with NEW guids, no parents, source="immigrant", origin="immigrant"
        role=PromptTag(
            guid=str(uuid4()),  # NEW guid
            text=tags_dict["role"],
            parent_tag_guid=None,  # No parent
            source="immigrant",    # NOT "initial"
            origin="immigrant"     # Originated from immigration
        ),
        compression_target=PromptTag(
            guid=str(uuid4()),
            text=tags_dict["compression_target"],
            parent_tag_guid=None,
            source="immigrant",
            origin="immigrant"
        ),
        fidelity=PromptTag(
            guid=str(uuid4()),
            text=tags_dict["fidelity"],
            parent_tag_guid=None,
            source="immigrant",
            origin="immigrant"
        ),
        constraints=PromptTag(
            guid=str(uuid4()),
            text=tags_dict["constraints"],
            parent_tag_guid=None,
            source="immigrant",
            origin="immigrant"
        ),
        output=PromptTag(
            guid=str(uuid4()),
            text=tags_dict["output"],
            parent_tag_guid=None,
            source="immigrant",
            origin="immigrant"
        ),

        # Evaluation fields remain None (unevaluated)
        fitness=None,
        original_text=None,
        compressed_text=None,
        original_words=None,
        compressed_words=None,
        compression_ratio=None,
        quality_scores=None,
        quality_score_avg=None,
        survival_factor=None
    )
