#!/usr/bin/env python3
"""
Run complete genetic algorithm experiment (Gen 0 → Evolution → Analysis).

This script combines all phases into a single execution:
1. Create Generation 0 (initial population)
2. Run evolution for N generations
3. Save results and statistics

This is the simplest way to run a complete experiment from start to finish.

Usage:
    # Quick test (5 prompts, 5 generations)
    python scripts/run_experiment.py --era quicktest --population 5 --generations 5

    # Standard test (20 prompts, 10 generations)
    python scripts/run_experiment.py --era test-1 --population 20 --generations 10

    # Production run (100 prompts, 20 generations)
    python scripts/run_experiment.py --era mixed-1 --population 100 --generations 20
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.couchbase_client import CouchbaseClient
from src.initial_prompts import create_generation_zero
from src.evolution import run_evolution


def main():
    parser = argparse.ArgumentParser(
        description="""Run complete genetic algorithm experiment (Gen 0 → Evolution).

This script creates Generation 0 and evolves it for N generations in a single
execution. It is INTERACTIVE and will ask for confirmation before starting.

For non-interactive automated runs, use run_full_experiment.py instead.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test - Fast iteration for testing setup
  python scripts/run_experiment.py --era quicktest --population 5 --generations 5
  (Estimated: 5-10 minutes, $1-3)

  # Standard test - Verify GA dynamics
  python scripts/run_experiment.py --era test-1 --population 20 --generations 10
  (Estimated: 30-60 minutes, $10-30)

  # Production run - Full research experiment
  python scripts/run_experiment.py --era mixed-1 --population 100 --generations 20
  (Estimated: 4-8 hours, $100-300)

  # Custom parameters - Fine-tune GA behavior
  python scripts/run_experiment.py --era custom-1 --population 20 --generations 10 \\
    --elite 0.25 --mutation-fraction 0.15 --immigration-fraction 0.1

For more information, see project documentation in /project_docs/
        """
    )

    # Required arguments
    required = parser.add_argument_group('Required Arguments')
    required.add_argument(
        "--era",
        required=True,
        metavar="ERA",
        help="Unique experiment identifier (e.g., 'test-1', 'mixed-1', 'quicktest'). "
             "Used to track all prompts and results for this experiment."
    )

    required.add_argument(
        "--generations",
        type=int,
        required=True,
        metavar="N",
        help="Maximum generations to evolve. Evolution may stop earlier if convergence "
             "detected. Typical values: 5-10 for tests, 20+ for production."
    )

    # Population & Model Configuration
    config = parser.add_argument_group('Population & Model Configuration')
    config.add_argument(
        "--population",
        type=int,
        default=20,
        metavar="SIZE",
        help="Number of prompts per generation. Larger populations provide better "
             "exploration but increase API costs. (default: %(default)s, production: 100)"
    )

    config.add_argument(
        "--model",
        choices=["claude", "openai", "gemini", "gemini3"],
        default="claude",
        metavar="MODEL",
        help="Model used for compression execution (NOT for prompt generation, which "
             "uses random selection across all models). All prompts in this era will "
             "be compressed using this model. Choices: %(choices)s (default: %(default)s)"
    )

    # Genetic Algorithm Parameters
    ga_params = parser.add_argument_group('Genetic Algorithm Parameters')
    ga_params.add_argument(
        "--elite",
        type=float,
        default=0.2,
        metavar="FRACTION",
        help="Elite fraction: top performers preserved unchanged each generation. "
             "Higher values = more exploitation, lower = more exploration. "
             "Range: 0.1-0.3, recommended: 0.2 (default: %(default)s)"
    )

    ga_params.add_argument(
        "--mutation-fraction",
        type=float,
        default=0.2,
        metavar="FRACTION",
        help="Fraction of population created via mutation. Higher = more variation. "
             "Range: 0.1-0.3, recommended: 0.2 (default: %(default)s)"
    )

    ga_params.add_argument(
        "--tags-per-mutation",
        type=int,
        default=1,
        metavar="COUNT",
        help="Number of tags modified per mutation. Lower = finer changes, "
             "higher = more radical changes. Range: 1-2 (default: %(default)s)"
    )

    ga_params.add_argument(
        "--immigration-fraction",
        type=float,
        default=0.08,
        metavar="FRACTION",
        help="Fraction of population created via fresh random prompts on ODD "
             "generations only. Prevents local optima. Range: 0.05-0.15, "
             "recommended: 0.08 (default: %(default)s)"
    )

    ga_params.add_argument(
        "--prompt-temp",
        type=float,
        default=1.0,
        metavar="TEMP",
        help="Temperature for prompt generation (initial, mutation, immigration). "
             "Higher = more creative/variable. Range: 0.0-2.0, but Claude caps at 1.0. "
             "(default: %(default)s)"
    )

    ga_params.add_argument(
        "--single-tag",
        action="store_true",
        default=False,
        help="Enable single-tag mode: mutate/crossover only 1 tag per operation. "
             "Forces --tags-per-mutation=1. Enables clearer phylogenetic attribution "
             "tracking for Paper 2 analysis. (default: disabled)"
    )

    # Convergence Settings
    convergence = parser.add_argument_group('Convergence Settings')
    convergence.add_argument(
        "--convergence-window",
        type=int,
        default=3,
        metavar="GENS",
        help="Number of generations to check for fitness plateau. "
             "(default: %(default)s)"
    )

    convergence.add_argument(
        "--convergence-threshold",
        type=float,
        default=0.05,
        metavar="CHANGE",
        help="Maximum fitness change (as fraction) to consider converged. "
             "Lower = stricter convergence. (default: %(default)s = 5%%)"
    )

    convergence.add_argument(
        "--no-convergence-stop",
        action="store_true",
        default=False,
        help="Continue evolution even if convergence detected. Use for research "
             "exploring post-convergence dynamics. (default: stop on convergence)"
    )

    # Evaluation Options
    evaluation = parser.add_argument_group('Evaluation Options')
    evaluation.add_argument(
        "--token-eval",
        action="store_true",
        default=False,
        help="Use token-based compression ratio for fitness calculation instead of "
             "word-based. Token-based is more precise but word-based is faster. "
             "(default: word-based)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.population < 5:
        print("ERROR: Population size must be at least 5")
        sys.exit(1)

    if args.generations < 1:
        print("ERROR: Must evolve at least 1 generation")
        sys.exit(1)

    # Validate temperature (OpenAI max is 2.0, Claude max is 1.0)
    if args.prompt_temp < 0 or args.prompt_temp > 2.0:
        print(f"ERROR: --prompt-temp must be between 0.0 and 2.0, got {args.prompt_temp}")
        sys.exit(1)
    if args.prompt_temp > 1.0:
        print(f"WARNING: --prompt-temp {args.prompt_temp} exceeds Claude's max (1.0). Claude calls will use 1.0.")

    # Single-tag mode forces tags_per_mutation=1
    if args.single_tag:
        if args.tags_per_mutation != 1:
            print(f"INFO: --single-tag mode forces --tags-per-mutation=1 (was {args.tags_per_mutation})")
            args.tags_per_mutation = 1

    # Calculate estimates
    total_prompts = args.population + (args.generations * args.population)
    estimated_minutes = total_prompts * 10 / 60
    estimated_cost_low = total_prompts * 0.05
    estimated_cost_high = total_prompts * 0.15

    # Determine fitness metric
    fitness_metric = "tokens" if args.token_eval else "words"

    # Print experiment plan
    print("=" * 70)
    print("COMPLETE GENETIC ALGORITHM EXPERIMENT")
    print("=" * 70)
    print(f"Era:               {args.era}")
    print(f"Population Size:   {args.population}")
    print(f"Max Generations:   {args.generations} (Gen 0 → Gen {args.generations})")
    print(f"Compression Model: {args.model}")
    print(f"Fitness Metric:    {fitness_metric}")
    print()
    print("GA Parameters:")
    print(f"  Elite Fraction:      {args.elite:.1%}")
    print(f"  Mutation Fraction:   {args.mutation_fraction:.1%} ({args.tags_per_mutation} tag(s) each)")
    print(f"  Immigration Fraction: {args.immigration_fraction:.1%} (odd gens only)")
    print(f"  Conv. Window:        {args.convergence_window} gen(s)")
    print(f"  Conv. Threshold:     {args.convergence_threshold:.2%}")
    print(f"  Stop on Convergence: {not args.no_convergence_stop}")
    print()
    print(f"Total Prompts:     ~{total_prompts} (Gen 0 + {args.generations} evolutions)")
    print(f"Estimated Time:    ~{estimated_minutes:.0f} minutes ({estimated_minutes/60:.1f} hours)")
    print(f"Estimated Cost:    ${estimated_cost_low:.2f} - ${estimated_cost_high:.2f}")
    print("=" * 70)
    print()

    # Confirm
    response = input(f"Run complete experiment for era '{args.era}'? (y/n): ")
    if response.lower() != 'y':
        print("Aborted.")
        sys.exit(0)

    start_time = datetime.now()
    experiment_results = {
        "era": args.era,
        "population_size": args.population,
        "compression_model": args.model,
        "fitness_metric": fitness_metric,
        "start_time": start_time.isoformat(),
        "gen0_stats": None,
        "evolution_stats": None,
        "end_time": None,
        "total_duration_seconds": None
    }

    # Connect to Couchbase
    try:
        with CouchbaseClient() as cb:
            print("✓ Connected to Couchbase\n")

            # Phase 1: Create Generation 0
            print("\n" + "=" * 70)
            print("PHASE 1: CREATING GENERATION 0")
            print("=" * 70)

            gen0_stats = create_generation_zero(
                era=args.era,
                population_size=args.population,
                compression_model=args.model,
                couchbase_client=cb,
                use_token_metric=args.token_eval,
                prompt_temperature=args.prompt_temp,
                single_tag=args.single_tag
            )

            experiment_results["gen0_stats"] = gen0_stats

            print(f"\n✓ Generation 0 created successfully!")
            print(f"   Mean fitness: {gen0_stats['mean_fitness']:.4f}")
            print(f"   Time: {gen0_stats['elapsed_seconds']/60:.1f} minutes")

            # Phase 2: Run evolution
            print("\n" + "=" * 70)
            print("PHASE 2: RUNNING EVOLUTION")
            print("=" * 70)

            evolution_stats = run_evolution(
                era=args.era,
                starting_generation=0,
                num_generations=args.generations,
                couchbase_client=cb,
                compression_model=args.model,
                population_size=args.population,
                elite_fraction=args.elite,
                mutation_fraction=args.mutation_fraction,
                immigration_fraction=args.immigration_fraction,
                tags_per_mutation=args.tags_per_mutation,
                convergence_window=args.convergence_window,
                convergence_threshold=args.convergence_threshold,
                check_convergence=not args.no_convergence_stop,
                use_token_metric=args.token_eval,
                prompt_temperature=args.prompt_temp,
                single_tag=args.single_tag
            )

            experiment_results["evolution_stats"] = evolution_stats

            # Calculate final results
            end_time = datetime.now()
            experiment_results["end_time"] = end_time.isoformat()
            experiment_results["total_duration_seconds"] = (end_time - start_time).total_seconds()

            # Print final summary
            print("\n" + "=" * 70)
            print("EXPERIMENT COMPLETE")
            print("=" * 70)
            print(f"Era:                {args.era}")
            print(f"Generations Evolved: {len(evolution_stats)}")
            print()
            print("Generation 0:")
            print(f"  Mean Fitness:     {gen0_stats['mean_fitness']:.4f}")
            print(f"  Max Fitness:      {gen0_stats['max_fitness']:.4f}")
            print()
            print(f"Final Generation ({evolution_stats[-1]['generation']}):")
            print(f"  Mean Fitness:     {evolution_stats[-1]['mean_fitness']:.4f}")
            print(f"  Max Fitness:      {evolution_stats[-1]['max_fitness']:.4f}")
            print()

            # Calculate improvement
            initial_mean = gen0_stats['mean_fitness']
            final_mean = evolution_stats[-1]['mean_fitness']
            improvement = ((final_mean - initial_mean) / initial_mean) * 100
            print(f"Fitness Improvement: {improvement:+.1f}%")
            print()

            total_minutes = experiment_results["total_duration_seconds"] / 60
            print(f"Total Time:         {total_minutes:.1f} minutes ({total_minutes/60:.2f} hours)")
            print("=" * 70)

            # Save complete experiment results
            output_file = Path("tmp") / f"experiment_{args.era}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            output_file.parent.mkdir(exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(experiment_results, f, indent=2)

            print(f"\n✓ Complete results saved to: {output_file}")
            print(f"\n✓ Experiment completed successfully!")
            print(f"\nQuery results in Couchbase:")
            print(f"  SELECT * FROM prompts WHERE era = '{args.era}' ORDER BY generation, fitness DESC;")
            print(f"  SELECT * FROM generations WHERE era = '{args.era}' ORDER BY generation;")

    except KeyboardInterrupt:
        print("\n\n✗ Experiment interrupted by user")
        end_time = datetime.now()
        experiment_results["end_time"] = end_time.isoformat()
        experiment_results["total_duration_seconds"] = (end_time - start_time).total_seconds()
        experiment_results["status"] = "interrupted"

        # Save partial results
        output_file = Path("tmp") / f"experiment_{args.era}_INTERRUPTED_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(experiment_results, f, indent=2)
        print(f"Partial results saved to: {output_file}")
        sys.exit(1)

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

        end_time = datetime.now()
        experiment_results["end_time"] = end_time.isoformat()
        experiment_results["total_duration_seconds"] = (end_time - start_time).total_seconds()
        experiment_results["status"] = "failed"
        experiment_results["error"] = str(e)

        # Save partial results
        output_file = Path("tmp") / f"experiment_{args.era}_FAILED_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_file.parent.mkdir(exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(experiment_results, f, indent=2)
        print(f"Partial results saved to: {output_file}")
        sys.exit(1)


if __name__ == "__main__":
    main()
