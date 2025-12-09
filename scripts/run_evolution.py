#!/usr/bin/env python3
"""
Run genetic algorithm evolution experiment.

This script evolves prompts from one generation to the next using genetic
operators (selection, crossover, mutation, immigration). It can start from
any generation and automatically detects convergence to stop early.

Usage:
    # Evolve from Generation 0 for 10 generations
    python scripts/run_evolution.py --era test-1 --generations 10

    # Resume from Generation 5
    python scripts/run_evolution.py --era test-1 --start 5 --generations 5

    # Full production run with custom parameters
    python scripts/run_evolution.py --era mixed-1 --generations 20 --population 100
"""

import argparse
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.couchbase_client import CouchbaseClient
from src.evolution import run_evolution


def main():
    parser = argparse.ArgumentParser(
        description="""Run genetic algorithm evolution (Evolution Only - Requires Existing Gen 0).

This script evolves prompts from one generation to the next using genetic
operators (selection, crossover, mutation, immigration). It can start from
any generation and automatically detects convergence to stop early.

IMPORTANT: This script requires Generation 0 to already exist. To create Gen 0
and run evolution in one step, use run_experiment.py or run_full_experiment.py instead.

This script supports RESUMING experiments using the --start parameter.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evolve from Gen 0 for 10 generations
  python scripts/run_evolution.py --era test-1 --generations 10
  (Estimated: 30-50 minutes for 20 prompts, $10-30)

  # Resume from Gen 5 - Continue interrupted experiment
  python scripts/run_evolution.py --era test-1 --start 5 --generations 5
  (Useful after interruptions or to extend experiments)

  # Production run - Larger population
  python scripts/run_evolution.py --era mixed-1 --generations 20 --population 100
  (Estimated: 6-10 hours, $200-600)

  # Custom GA parameters - Fine-tune behavior
  python scripts/run_evolution.py --era test-1 --generations 10 \\
    --elite 0.25 --mutation-fraction 0.15 --immigration-fraction 0.1

  # Disable convergence checking - Force full run
  python scripts/run_evolution.py --era test-1 --generations 10 --no-convergence-stop

For more information, see project documentation in /project_docs/
        """
    )

    # Required arguments
    required = parser.add_argument_group('Required Arguments')
    required.add_argument(
        "--era",
        required=True,
        metavar="ERA",
        help="Era identifier for existing experiment (e.g., 'test-1', 'mixed-1'). "
             "Must have Generation 0 already created."
    )

    required.add_argument(
        "--generations",
        type=int,
        required=True,
        metavar="N",
        help="Maximum number of generations to evolve. Evolution may stop earlier "
             "if convergence detected. Typical: 5-10 for tests, 20+ for production."
    )

    # Evolution Configuration
    evolution_config = parser.add_argument_group('Evolution Configuration')
    evolution_config.add_argument(
        "--start",
        type=int,
        default=0,
        metavar="GEN",
        help="Starting generation number. Use 0 to evolve from Gen 0, or higher "
             "values to resume interrupted experiments. (default: %(default)s)"
    )

    evolution_config.add_argument(
        "--population",
        type=int,
        default=20,
        metavar="SIZE",
        help="Population size (must match the population in the starting generation). "
             "(default: %(default)s, production: 100)"
    )

    evolution_config.add_argument(
        "--model",
        choices=["claude", "openai", "gemini", "gemini3"],
        default="claude",
        metavar="MODEL",
        help="Model used for compression execution. Should match the model used in "
             "earlier generations for consistency. Choices: %(choices)s (default: %(default)s)"
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
    if args.generations < 1:
        print("ERROR: Must evolve at least 1 generation")
        sys.exit(1)

    if args.elite < 0.1 or args.elite > 0.5:
        print("WARNING: Unusual elite fraction. Recommended: 0.15 - 0.25")

    if args.population < 10:
        print("ERROR: Population size must be at least 10")
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
    target_generation = args.start + args.generations
    estimated_minutes = args.generations * args.population * 10 / 60
    estimated_cost_low = args.generations * args.population * 0.05
    estimated_cost_high = args.generations * args.population * 0.15

    # Determine fitness metric
    fitness_metric = "tokens" if args.token_eval else "words"

    # Print configuration
    print("=" * 60)
    print("EVOLUTION EXPERIMENT")
    print("=" * 60)
    print(f"Era:               {args.era}")
    print(f"Starting Gen:      {args.start}")
    print(f"Target Gen:        {target_generation}")
    print(f"Max Generations:   {args.generations}")
    print(f"Population Size:   {args.population}")
    print(f"Compression Model: {args.model}")
    print(f"Fitness Metric:    {fitness_metric}")
    print()
    print("GA Parameters:")
    print(f"  Elite Fraction:      {args.elite:.1%}")
    print(f"  Mutation Fraction:   {args.mutation_fraction:.1%} ({args.tags_per_mutation} tag(s) each)")
    print(f"  Immigration Fraction: {args.immigration_fraction:.1%} (odd gens only)")
    print(f"  Conv. Window:        {args.convergence_window} gen(s)")
    print(f"  Conv. Threshold:     {args.convergence_threshold:.2%}")
    print()
    print(f"Estimated Time:    ~{estimated_minutes:.0f} minutes (may stop early)")
    print(f"Estimated Cost:    ${estimated_cost_low:.2f} - ${estimated_cost_high:.2f}")
    print("=" * 60)
    print()

    # Confirm for large runs
    if args.generations >= 10 or args.population >= 50:
        response = input(f"Run evolution for {args.generations} generations? (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    # Connect to Couchbase and run evolution
    try:
        with CouchbaseClient() as cb:
            print("✓ Connected to Couchbase\n")

            all_stats = run_evolution(
                era=args.era,
                starting_generation=args.start,
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

            # Print summary
            print("\n" + "=" * 60)
            print("EVOLUTION COMPLETE")
            print("=" * 60)
            print(f"Generations Evolved: {len(all_stats)}")
            print()
            print("Generation Summary:")
            print("-" * 60)
            for stats in all_stats:
                gen = stats['generation']
                mean = stats['mean_fitness']
                max_fit = stats['max_fitness']
                elapsed = stats['elapsed_seconds']
                print(f"  Gen {gen:2d}: mean={mean:6.4f}, max={max_fit:6.4f}, time={elapsed/60:4.1f}min")
            print("=" * 60)

            # Calculate improvement
            if len(all_stats) > 1:
                initial_mean = all_stats[0]['mean_fitness']
                final_mean = all_stats[-1]['mean_fitness']
                improvement = ((final_mean - initial_mean) / initial_mean) * 100
                print(f"\nFitness Improvement: {improvement:+.1f}%")

            # Save stats to file
            output_file = Path("tmp") / f"evolution_stats_{args.era}_{args.start}-{args.start + len(all_stats) - 1}.json"
            output_file.parent.mkdir(exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(all_stats, f, indent=2)
            print(f"\n✓ Statistics saved to: {output_file}")

            print(f"\n✓ Evolution completed successfully!")
            print(f"\nNext step: Analyze results with:")
            print(f"  python scripts/analyze_results.py --era {args.era}")

    except KeyboardInterrupt:
        print("\n\n✗ Evolution interrupted by user")
        print(f"\nTo resume from where you left off:")
        print(f"  python scripts/run_evolution.py --era {args.era} --start <last_completed_gen + 1> --generations <remaining_gens>")
        sys.exit(1)

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print(f"\nTo resume from where you left off:")
        print(f"  python scripts/run_evolution.py --era {args.era} --start <last_completed_gen + 1> --generations <remaining_gens>")
        sys.exit(1)


if __name__ == "__main__":
    main()
