#!/usr/bin/env python3
"""
Create Generation 0 for genetic algorithm evolution.

This script creates the initial population of prompts that will evolve
through the genetic algorithm. It generates N prompts using random LLM
selection, evaluates their fitness, and stores them in Couchbase.

Usage:
    # Test with small population
    python scripts/create_generation_zero.py --era test-1 --population 20 --model claude

    # Production run
    python scripts/create_generation_zero.py --era mixed-1 --population 100 --model claude

    # Quick test
    python scripts/create_generation_zero.py --era quicktest --population 5 --model openai
"""

import argparse
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.couchbase_client import CouchbaseClient
from src.initial_prompts import create_generation_zero


def main():
    parser = argparse.ArgumentParser(
        description="Create Generation 0 for genetic algorithm evolution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test run with 20 prompts
  python scripts/create_generation_zero.py --era test-1 --population 20

  # Production run with 100 prompts
  python scripts/create_generation_zero.py --era mixed-1 --population 100

  # Quick test with 5 prompts
  python scripts/create_generation_zero.py --era quicktest --population 5
        """
    )

    parser.add_argument(
        "--era",
        required=True,
        help="Era identifier (e.g., 'test-1', 'mixed-1')"
    )

    parser.add_argument(
        "--population",
        type=int,
        default=20,
        help="Population size (default: 20 for testing, use 100 for production)"
    )

    parser.add_argument(
        "--model",
        choices=["claude", "openai", "gemini", "gemini3"],
        default="claude",
        help="Model to use for compression execution (default: claude)"
    )

    args = parser.parse_args()

    # Validate population size
    if args.population < 5:
        print("ERROR: Population size must be at least 5")
        sys.exit(1)

    if args.population > 20 and args.population < 100:
        print(f"WARNING: Unusual population size {args.population}. "
              "Recommended: 20 (test) or 100 (production)")

    # Print configuration
    print("=" * 60)
    print("GENERATION 0 CREATION")
    print("=" * 60)
    print(f"Era:              {args.era}")
    print(f"Population Size:  {args.population}")
    print(f"Compression Model: {args.model}")
    print(f"\nEstimated Time:   ~{args.population * 10 / 60:.1f} minutes")
    print(f"Estimated Cost:   ${args.population * 0.10:.2f} - ${args.population * 0.20:.2f}")
    print("=" * 60)
    print()

    # Confirm for large populations
    if args.population >= 50:
        response = input(f"Create {args.population} prompts? This will take ~{args.population * 10 / 60:.0f} minutes. (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    # Connect to Couchbase and create Generation 0
    try:
        with CouchbaseClient() as cb:
            print("✓ Connected to Couchbase\n")

            stats = create_generation_zero(
                era=args.era,
                population_size=args.population,
                compression_model=args.model,
                couchbase_client=cb
            )

            # Print results
            print("\n" + "=" * 60)
            print("GENERATION 0 COMPLETE")
            print("=" * 60)
            print(f"Era:              {stats['era']}")
            print(f"Generation:       {stats['generation']}")
            print(f"Population Size:  {stats['population_size']}")
            print(f"Success Count:    {stats['success_count']}")
            print()
            print("Fitness Statistics:")
            print(f"  Mean:   {stats['mean_fitness']:.4f}")
            print(f"  Std:    {stats['std_fitness']:.4f}")
            print(f"  Median: {stats['median_fitness']:.4f}")
            print(f"  Min:    {stats['min_fitness']:.4f}")
            print(f"  Max:    {stats['max_fitness']:.4f}")
            print()
            print(f"Elapsed Time:     {stats['elapsed_seconds']:.1f}s ({stats['elapsed_seconds']/60:.1f} min)")
            print(f"Throughput:       {stats['prompts_per_minute']:.1f} prompts/min")
            print("=" * 60)

            # Save stats to file
            output_file = Path("tmp") / f"gen0_stats_{args.era}.json"
            output_file.parent.mkdir(exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(stats, f, indent=2)
            print(f"\n✓ Statistics saved to: {output_file}")

            print(f"\n✓ Generation 0 created successfully!")
            print(f"\nNext step: Run evolution with:")
            print(f"  python scripts/run_evolution.py --era {args.era} --generations 10")

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
