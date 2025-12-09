"""
Flask Visualization Dashboard for Genetic Algorithm Evolution

This standalone web app visualizes evolution data from Couchbase, providing
insights into fitness trajectories, operator effectiveness, and diversity
patterns across generations.

Architecture:
- Flask serves API endpoints that query Couchbase
- Frontend uses Plotly.js for interactive charts
- Single-page dashboard (no page navigation)

Used by: Researchers analyzing evolution results
Requires: Couchbase connection, evolution data in database
Related: src/evolution.py (data producer), project_docs/phylo_data.md (query patterns)
"""

from flask import Flask, render_template, jsonify, request
import sys
import os

# Add parent directory to path to import from /src/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.couchbase_client import CouchbaseClient

app = Flask(__name__)

# Global CouchbaseClient (initialized on first request)
cb_client = None

def get_db():
    """
    Get or create CouchbaseClient connection (lazy initialization).

    Returns:
        CouchbaseClient: Active database connection
    """
    global cb_client
    if cb_client is None:
        cb_client = CouchbaseClient()
        cb_client.__enter__()  # Establish connection
    return cb_client


@app.route('/')
def index():
    """Serve dashboard HTML page."""
    return render_template('dashboard.html')


@app.route('/lineage')
def lineage_explorer():
    """Serve lineage explorer page with interactive Sankey visualization."""
    return render_template('lineage.html')


@app.route('/phylo_attribution')
def phylo_attribution():
    """
    Serve phylogenetic attribution analysis page.

    Uses single-tag mutation eras to trace which tag changes drive fitness improvements.
    Provides three views:
    1. Static metrics - mean fitness/quality/compression per tag variant
    2. Delta analysis - which tag types cause fitness changes
    3. Lineage tracing - evolutionary ancestry of specific tags
    """
    return render_template('phylo_attribution.html')


@app.route('/api/eras')
def get_eras():
    """
    List all eras with metadata.

    Returns:
        JSON array of era objects: [{"era": "mixed-1", "max_generation": 19, "total_prompts": 1500}, ...]

    Error Handling:
        Returns 500 with error message if database query fails
    """
    try:
        cb = get_db()

        # Query distinct eras from generations collection
        query = f"""
            SELECT era,
                   MAX(generation) as max_generation,
                   COUNT(*) as total_prompts
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations`
            GROUP BY era
            ORDER BY era
        """

        results = cb.cluster.query(query)
        eras = [row for row in results]

        return jsonify(eras)

    except Exception as e:
        # Fail-loud: return error with 500 status
        return jsonify({"error": str(e)}), 500


@app.route('/api/generations/<era>')
def get_generations(era):
    """
    Get generation statistics for an era.

    Returns generation-level aggregated statistics from 'generations' collection.
    This is MUCH faster than querying all prompts.

    Args:
        era: Era identifier (e.g., "mixed-1")

    Returns:
        JSON array of generation stats: [
            {
                "generation": 0,
                "mean_fitness": 12.4,
                "std_fitness": 2.1,
                "population_size": 100,
                ...
            },
            ...
        ]

    Error Handling:
        Returns 404 if era not found
        Returns 500 if database query fails
    """
    try:
        cb = get_db()

        query = f"""
            SELECT gs.*
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generation_stats` gs
            WHERE gs.era = '{era}'
            ORDER BY gs.generation
        """

        results = cb.cluster.query(query)
        stats = [row for row in results]

        if len(stats) == 0:
            return jsonify({"error": f"No generation data found for era '{era}'"}), 404

        return jsonify(stats)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/prompts/<era>')
def get_prompts(era):
    """
    Get all prompts for an era (with optional generation filter).

    Query params:
        generation (optional): Filter to specific generation

    Returns:
        JSON array of prompt objects with fitness and type data

    Error Handling:
        Returns 500 if database query fails
    """
    try:
        cb = get_db()
        generation = request.args.get('generation', type=int)

        # Build query with optional generation filter
        where_clause = f"p.era = '{era}'"
        if generation is not None:
            where_clause += f" AND p.generation = {generation}"

        query = f"""
            SELECT p.prompt_id, p.generation, p.`type`, p.fitness,
                   p.compression_ratio, p.quality_score_avg,
                   p.`role`.guid as role_guid, p.`role`.origin as role_origin,
                   p.compression_target.guid as comp_guid,
                   p.fidelity.guid as fidelity_guid,
                   p.constraints.guid as constraints_guid,
                   p.`output`.guid as output_guid
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
            WHERE {where_clause}
            ORDER BY p.generation, p.fitness DESC
        """

        results = cb.cluster.query(query)
        prompts = [row for row in results]

        return jsonify(prompts)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/diversity/<era>')
def get_tag_diversity(era):
    """
    Get tag diversity metrics per generation.

    Counts unique tag guids for each tag type per generation.
    Shows convergence (diversity decreases) vs sustained diversity.

    Args:
        era: Era identifier

    Returns:
        JSON array: [
            {
                "generation": 0,
                "role_unique": 80,
                "comp_unique": 75,
                "fidelity_unique": 82,
                "constraints_unique": 78,
                "output_unique": 81,
                "population_size": 100
            },
            ...
        ]

    Error Handling:
        Returns 500 if database query fails
    """
    try:
        cb = get_db()

        query = f"""
            SELECT
                p.generation,
                COUNT(DISTINCT p.`role`.guid) as role_unique,
                COUNT(DISTINCT p.compression_target.guid) as comp_unique,
                COUNT(DISTINCT p.fidelity.guid) as fidelity_unique,
                COUNT(DISTINCT p.constraints.guid) as constraints_unique,
                COUNT(DISTINCT p.`output`.guid) as output_unique,
                COUNT(*) as population_size
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
            WHERE p.era = '{era}'
            GROUP BY p.generation
            ORDER BY p.generation
        """

        results = cb.cluster.query(query)
        diversity = [row for row in results]

        return jsonify(diversity)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tree/<era>')
def get_tree_data(era):
    """
    Get all prompts with full tag data for phylogenetic tree visualization.

    Returns complete prompt data including:
    - All evaluation metrics (fitness, compression_ratio, quality_score)
    - Parents array for edge construction
    - All 5 tags with full details (guid, text, origin, source, parent_tag_guid)

    IMPORTANT: Uses composite key (prompt_id + generation) to handle elite inheritance.
    Elite prompts have same prompt_id across generations, so we concatenate with
    generation to create unique node IDs for the Sankey diagram.

    Args:
        era: Era identifier

    Returns:
        JSON array of complete prompt objects for tree visualization

    Error Handling:
        Returns 500 if database query fails
    """
    try:
        cb = get_db()

        query = f"""
            SELECT
                CONCAT(p.prompt_id, "-gen-", TO_STRING(p.generation)) as prompt_id,
                p.generation,
                p.`type`,
                CASE
                    WHEN p.parents IS NULL THEN NULL
                    WHEN ARRAY_LENGTH(p.parents) = 0 THEN NULL
                    ELSE ARRAY CONCAT(parent_id, "-gen-", TO_STRING(p.generation - 1)) FOR parent_id IN p.parents END
                END as parents,
                p.fitness,
                p.compression_ratio,
                p.quality_score_avg,
                p.model_used,

                -- Full role tag
                p.`role`.guid as role_guid,
                p.`role`.text as role_text,
                p.`role`.origin as role_origin,
                p.`role`.source as role_source,
                p.`role`.parent_tag_guid as role_parent_guid,

                -- Full compression_target tag
                p.compression_target.guid as comp_guid,
                p.compression_target.text as comp_text,
                p.compression_target.origin as comp_origin,
                p.compression_target.source as comp_source,
                p.compression_target.parent_tag_guid as comp_parent_guid,

                -- Full fidelity tag
                p.fidelity.guid as fidelity_guid,
                p.fidelity.text as fidelity_text,
                p.fidelity.origin as fidelity_origin,
                p.fidelity.source as fidelity_source,
                p.fidelity.parent_tag_guid as fidelity_parent_guid,

                -- Full constraints tag
                p.constraints.guid as constraints_guid,
                p.constraints.text as constraints_text,
                p.constraints.origin as constraints_origin,
                p.constraints.source as constraints_source,
                p.constraints.parent_tag_guid as constraints_parent_guid,

                -- Full output tag
                p.`output`.guid as output_guid,
                p.`output`.text as output_text,
                p.`output`.origin as output_origin,
                p.`output`.source as output_source,
                p.`output`.parent_tag_guid as output_parent_guid

            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
            WHERE p.era = '{era}'
            ORDER BY p.generation, p.fitness DESC
        """

        results = cb.cluster.query(query)
        prompts = [row for row in results]

        return jsonify(prompts)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# PHYLOGENETIC ATTRIBUTION ANALYSIS ENDPOINTS
#
# These endpoints support phylogenetic attribution analysis - understanding
# which tag changes cause fitness improvements by tracing evolutionary lineage.
#
# Only works with single_tag=true eras where mutations change exactly one tag,
# enabling clean attribution of fitness deltas to specific tag mutations.
# ============================================================================

@app.route('/api/phylo_attribution/eras')
def get_phylo_attribution_eras():
    """
    List eras suitable for phylogenetic attribution analysis (single_tag=true only).

    Phylogenetic attribution requires single-tag mutations to cleanly attribute
    fitness changes to specific tag modifications. Multi-tag mutations confound
    attribution since we can't isolate which tag caused the fitness change.

    Returns:
        JSON array of era objects: [
            {
                "era": "framework-v3-token-claude-phylo-2",
                "max_generation": 22,
                "total_prompts": 1150,
                "single_tag": true
            },
            ...
        ]

    Error Handling:
        Returns 500 with error message if database query fails
    """
    try:
        cb = get_db()

        query = f"""
            SELECT gs.era,
                   MAX(gs.generation) as max_generation,
                   SUM(gs.population_size) as total_prompts,
                   MIN(gs.single_tag) as single_tag
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generation_stats` gs
            WHERE gs.single_tag = true
            GROUP BY gs.era
            ORDER BY gs.era
        """

        results = cb.cluster.query(query)
        eras = [row for row in results]

        return jsonify(eras)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/phylo_attribution/tag_metrics/<era>')
def get_phylo_tag_metrics(era):
    """
    Get aggregated metrics for all tag variants in an era.

    Returns static metrics (mean fitness, quality, compression ratio)
    grouped by tag guid for each of the 5 tag types.

    Query params:
        tag_type (optional): Filter to specific tag type
        min_count (optional, default=2): Minimum prompt count to include variant

    Args:
        era: Era identifier

    Returns:
        JSON object with tag_types keys, each containing variants array:
        {
            "era": "framework-v3-token-claude-phylo-2",
            "tag_types": {
                "role": {
                    "variants": [
                        {
                            "guid": "abc-123",
                            "text": "Full tag text...",
                            "text_snippet": "Full tag text...",
                            "prompt_count": 45,
                            "mean_fitness": 0.72,
                            "std_fitness": 0.05,
                            "mean_quality": 8.2,
                            "mean_compression_ratio": 2.5,
                            "first_generation": 0,
                            "last_generation": 10,
                            "origin": "initial"
                        },
                        ...
                    ]
                },
                ...
            }
        }

    Error Handling:
        Returns 500 if database query fails
    """
    try:
        cb = get_db()
        tag_type_filter = request.args.get('tag_type', None)
        min_count = request.args.get('min_count', default=2, type=int)

        tag_types = ['role', 'compression_target', 'fidelity', 'constraints', 'output']
        if tag_type_filter:
            if tag_type_filter not in tag_types:
                return jsonify({"error": f"Invalid tag_type. Must be one of: {', '.join(tag_types)}"}), 400
            tag_types = [tag_type_filter]

        result = {
            "era": era,
            "tag_types": {}
        }

        for tag_type in tag_types:
            # Handle backtick escaping for reserved words
            tag_field = f'`{tag_type}`' if tag_type in ['role', 'output'] else tag_type

            query = f"""
                SELECT
                    p.{tag_field}.guid as guid,
                    SUBSTR(MIN(p.{tag_field}.text), 0, 50) as text_snippet,
                    MIN(p.{tag_field}.text) as text_full,
                    COUNT(*) as prompt_count,
                    AVG(p.fitness) as mean_fitness,
                    STDDEV(p.fitness) as std_fitness,
                    AVG(p.quality_score_avg) as mean_quality,
                    AVG(p.compression_ratio) as mean_compression_ratio,
                    MIN(p.generation) as first_generation,
                    MAX(p.generation) as last_generation,
                    MIN(p.{tag_field}.origin) as origin
                FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
                WHERE p.era = '{era}'
                GROUP BY p.{tag_field}.guid
                HAVING COUNT(*) >= {min_count}
                ORDER BY mean_fitness DESC
            """

            results = cb.cluster.query(query)
            variants = [row for row in results]

            result["tag_types"][tag_type] = {
                "variants": variants
            }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/phylo_attribution/tag_type_deltas/<era>')
def get_phylo_tag_type_deltas(era):
    """
    Get aggregate fitness deltas by tag type (which tag types drive improvement).

    For each of the 5 tag types, calculates the mean fitness change across ALL
    evolutionary operations (mutations + crossovers + elites). This shows which
    tag types drive overall fitness increases.

    In single-tag eras, when a tag changes (mutation), we can cleanly attribute
    the fitness delta to that specific tag type. For crossovers and elites, we
    measure the fitness impact of inheriting/preserving that tag.

    Args:
        era: Era identifier (must be single_tag=true era)

    Returns:
        JSON object with tag type delta statistics:
        {
            "era": "framework-v3-token-claude-phylo-2",
            "tag_type_deltas": [
                {
                    "tag_type": "role",
                    "mean_delta": 0.012,
                    "std_delta": 0.058,
                    "change_count": 890,
                    "mutation_count": 44,
                    "crossover_count": 780,
                    "elite_count": 66,
                    "positive_count": 512,
                    "negative_count": 378,
                    "positive_rate": 0.575
                },
                ...
            ]
        }

    Error Handling:
        Returns 500 if database query fails
    """
    try:
        cb = get_db()

        # Build single query with UNION ALL for all 5 tag types
        query = f"""
            SELECT
                'role' as tag_type,
                COUNT(*) as change_count,
                AVG(child.fitness - parent.fitness) as mean_delta,
                STDDEV(child.fitness - parent.fitness) as std_delta,
                IFNULL(SUM(CASE WHEN child.fitness > parent.fitness THEN 1 ELSE 0 END), 0) as positive_count,
                IFNULL(SUM(CASE WHEN child.fitness < parent.fitness THEN 1 ELSE 0 END), 0) as negative_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'mutation' THEN 1 ELSE 0 END), 0) as mutation_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'crossover' THEN 1 ELSE 0 END), 0) as crossover_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'elite' THEN 1 ELSE 0 END), 0) as elite_count
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` child
            UNNEST child.parents AS parent_id
            JOIN `{cb.bucket_name}`.`{cb.scope_name}`.`generations` parent
                ON parent.prompt_id = parent_id
                AND parent.generation = child.generation - 1
                AND parent.era = child.era
            WHERE child.era = '{era}'
              AND child.generation > 0
              AND child.`role`.guid != parent.`role`.guid

            UNION ALL

            SELECT
                'compression_target' as tag_type,
                COUNT(*) as change_count,
                AVG(child.fitness - parent.fitness) as mean_delta,
                STDDEV(child.fitness - parent.fitness) as std_delta,
                IFNULL(SUM(CASE WHEN child.fitness > parent.fitness THEN 1 ELSE 0 END), 0) as positive_count,
                IFNULL(SUM(CASE WHEN child.fitness < parent.fitness THEN 1 ELSE 0 END), 0) as negative_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'mutation' THEN 1 ELSE 0 END), 0) as mutation_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'crossover' THEN 1 ELSE 0 END), 0) as crossover_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'elite' THEN 1 ELSE 0 END), 0) as elite_count
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` child
            UNNEST child.parents AS parent_id
            JOIN `{cb.bucket_name}`.`{cb.scope_name}`.`generations` parent
                ON parent.prompt_id = parent_id
                AND parent.generation = child.generation - 1
                AND parent.era = child.era
            WHERE child.era = '{era}'
              AND child.generation > 0
              AND child.compression_target.guid != parent.compression_target.guid

            UNION ALL

            SELECT
                'fidelity' as tag_type,
                COUNT(*) as change_count,
                AVG(child.fitness - parent.fitness) as mean_delta,
                STDDEV(child.fitness - parent.fitness) as std_delta,
                IFNULL(SUM(CASE WHEN child.fitness > parent.fitness THEN 1 ELSE 0 END), 0) as positive_count,
                IFNULL(SUM(CASE WHEN child.fitness < parent.fitness THEN 1 ELSE 0 END), 0) as negative_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'mutation' THEN 1 ELSE 0 END), 0) as mutation_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'crossover' THEN 1 ELSE 0 END), 0) as crossover_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'elite' THEN 1 ELSE 0 END), 0) as elite_count
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` child
            UNNEST child.parents AS parent_id
            JOIN `{cb.bucket_name}`.`{cb.scope_name}`.`generations` parent
                ON parent.prompt_id = parent_id
                AND parent.generation = child.generation - 1
                AND parent.era = child.era
            WHERE child.era = '{era}'
              AND child.generation > 0
              AND child.fidelity.guid != parent.fidelity.guid

            UNION ALL

            SELECT
                'constraints' as tag_type,
                COUNT(*) as change_count,
                AVG(child.fitness - parent.fitness) as mean_delta,
                STDDEV(child.fitness - parent.fitness) as std_delta,
                IFNULL(SUM(CASE WHEN child.fitness > parent.fitness THEN 1 ELSE 0 END), 0) as positive_count,
                IFNULL(SUM(CASE WHEN child.fitness < parent.fitness THEN 1 ELSE 0 END), 0) as negative_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'mutation' THEN 1 ELSE 0 END), 0) as mutation_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'crossover' THEN 1 ELSE 0 END), 0) as crossover_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'elite' THEN 1 ELSE 0 END), 0) as elite_count
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` child
            UNNEST child.parents AS parent_id
            JOIN `{cb.bucket_name}`.`{cb.scope_name}`.`generations` parent
                ON parent.prompt_id = parent_id
                AND parent.generation = child.generation - 1
                AND parent.era = child.era
            WHERE child.era = '{era}'
              AND child.generation > 0
              AND child.constraints.guid != parent.constraints.guid

            UNION ALL

            SELECT
                'output' as tag_type,
                COUNT(*) as change_count,
                AVG(child.fitness - parent.fitness) as mean_delta,
                STDDEV(child.fitness - parent.fitness) as std_delta,
                IFNULL(SUM(CASE WHEN child.fitness > parent.fitness THEN 1 ELSE 0 END), 0) as positive_count,
                IFNULL(SUM(CASE WHEN child.fitness < parent.fitness THEN 1 ELSE 0 END), 0) as negative_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'mutation' THEN 1 ELSE 0 END), 0) as mutation_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'crossover' THEN 1 ELSE 0 END), 0) as crossover_count,
                IFNULL(SUM(CASE WHEN child.`type` = 'elite' THEN 1 ELSE 0 END), 0) as elite_count
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` child
            UNNEST child.parents AS parent_id
            JOIN `{cb.bucket_name}`.`{cb.scope_name}`.`generations` parent
                ON parent.prompt_id = parent_id
                AND parent.generation = child.generation - 1
                AND parent.era = child.era
            WHERE child.era = '{era}'
              AND child.generation > 0
              AND child.`output`.guid != parent.`output`.guid
        """

        results = list(cb.cluster.query(query))
        tag_type_deltas = []

        for result in results:
            if result.get('change_count', 0) > 0:
                # Calculate positive rate
                positive = result.get('positive_count', 0) or 0
                negative = result.get('negative_count', 0) or 0
                total = positive + negative
                result['positive_rate'] = positive / total if total > 0 else 0
                tag_type_deltas.append(result)

        # Sort by mean_delta descending (least harmful first)
        tag_type_deltas.sort(key=lambda x: x['mean_delta'], reverse=True)

        return jsonify({
            "era": era,
            "tag_type_deltas": tag_type_deltas
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/phylo_attribution/tag_lineage/<era>/<tag_guid>')
def get_phylo_tag_lineage(era, tag_guid):
    """
    Trace the evolutionary lineage of a specific tag variant.

    Walks up the parent_tag_guid chain to find all ancestors of a tag,
    and finds all children (mutations spawned from this tag).

    Args:
        era: Era identifier
        tag_guid: The guid of the tag to trace

    Query params:
        tag_type (optional): Specify which tag type this guid belongs to
                            If not provided, searches all tag types

    Returns:
        JSON object with lineage information:
        {
            "era": "framework-v3-token-claude-phylo-2",
            "tag_guid": "abc-123",
            "tag_type": "role",
            "lineage": {
                "current": {
                    "guid": "abc-123",
                    "text": "Full tag text...",
                    "origin": "mutation",
                    "parent_tag_guid": "xyz-789",
                    "first_generation": 5,
                    "last_generation": 10,
                    "prompt_count": 12,
                    "mean_fitness": 0.75
                },
                "ancestors": [
                    {
                        "guid": "xyz-789",
                        "text": "Parent tag text...",
                        "depth": 1,
                        ...
                    },
                    ...
                ],
                "children": [
                    {
                        "guid": "def-456",
                        "text": "Child tag text...",
                        ...
                    },
                    ...
                ]
            }
        }

    Error Handling:
        Returns 404 if tag guid not found
        Returns 500 if database query fails
    """
    try:
        cb = get_db()
        tag_type_filter = request.args.get('tag_type', None)

        # First, find which tag type this guid belongs to (if not specified)
        tag_types = ['role', 'compression_target', 'fidelity', 'constraints', 'output']
        if tag_type_filter:
            if tag_type_filter not in tag_types:
                return jsonify({"error": f"Invalid tag_type. Must be one of: {', '.join(tag_types)}"}), 400
            tag_types = [tag_type_filter]

        current_tag = None
        found_tag_type = None

        # Search for the tag across tag types
        for tag_type in tag_types:
            tag_field = f'`{tag_type}`' if tag_type in ['role', 'output'] else tag_type

            query = f"""
                SELECT
                    '{tag_type}' as tag_type,
                    p.{tag_field}.guid as guid,
                    p.{tag_field}.text as text,
                    p.{tag_field}.origin as origin,
                    p.{tag_field}.parent_tag_guid as parent_tag_guid,
                    MIN(p.generation) as first_generation,
                    MAX(p.generation) as last_generation,
                    COUNT(*) as prompt_count,
                    AVG(p.fitness) as mean_fitness
                FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
                WHERE p.era = '{era}'
                  AND p.{tag_field}.guid = '{tag_guid}'
                GROUP BY p.{tag_field}.guid, p.{tag_field}.text, p.{tag_field}.origin,
                         p.{tag_field}.parent_tag_guid
            """

            results = list(cb.cluster.query(query))
            if results:
                current_tag = results[0]
                found_tag_type = tag_type
                break

        if not current_tag:
            return jsonify({"error": f"Tag guid '{tag_guid}' not found in era '{era}'"}), 404

        # Now trace ancestors (walk up parent_tag_guid chain)
        ancestors = []
        current_parent_guid = current_tag.get('parent_tag_guid')
        depth = 1

        while current_parent_guid and depth < 20:  # Limit depth to prevent infinite loops
            tag_field = f'`{found_tag_type}`' if found_tag_type in ['role', 'output'] else found_tag_type

            query = f"""
                SELECT
                    p.{tag_field}.guid as guid,
                    p.{tag_field}.text as text,
                    p.{tag_field}.origin as origin,
                    p.{tag_field}.parent_tag_guid as parent_tag_guid,
                    MIN(p.generation) as first_generation,
                    MAX(p.generation) as last_generation,
                    COUNT(*) as prompt_count,
                    AVG(p.fitness) as mean_fitness
                FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
                WHERE p.era = '{era}'
                  AND p.{tag_field}.guid = '{current_parent_guid}'
                GROUP BY p.{tag_field}.guid, p.{tag_field}.text, p.{tag_field}.origin,
                         p.{tag_field}.parent_tag_guid
            """

            results = list(cb.cluster.query(query))
            if results:
                ancestor = results[0]
                ancestor['depth'] = depth
                ancestors.append(ancestor)
                current_parent_guid = ancestor.get('parent_tag_guid')
                depth += 1
            else:
                break

        # Find children (tags that have this tag as parent_tag_guid)
        tag_field = f'`{found_tag_type}`' if found_tag_type in ['role', 'output'] else found_tag_type

        query = f"""
            SELECT
                p.{tag_field}.guid as guid,
                p.{tag_field}.text as text,
                p.{tag_field}.origin as origin,
                MIN(p.generation) as first_generation,
                MAX(p.generation) as last_generation,
                COUNT(*) as prompt_count,
                AVG(p.fitness) as mean_fitness
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
            WHERE p.era = '{era}'
              AND p.{tag_field}.parent_tag_guid = '{tag_guid}'
            GROUP BY p.{tag_field}.guid, p.{tag_field}.text, p.{tag_field}.origin
        """

        results = cb.cluster.query(query)
        children = [row for row in results]

        return jsonify({
            "era": era,
            "tag_guid": tag_guid,
            "tag_type": found_tag_type,
            "lineage": {
                "current": current_tag,
                "ancestors": ancestors,
                "children": children
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# TAG EVOLUTIONARY STORY ENDPOINTS
#
# These endpoints tell the story of SUCCESSFUL tag evolution - which tags
# survived, which drove breakthroughs, and what patterns distinguish elites.
#
# CRITICAL: Requires single_tag = true eras (same as phylo_attribution)
# Single-tag eras enable clean tracking of individual tag variants across
# generations via GUIDs and parent_tag_guid lineage.
# ============================================================================

@app.route('/tag_story')
def tag_story():
    """
    Serve Tag Evolutionary Story page - three analyses of successful tag evolution:
    1. Tag Survival (founder effects) - which Gen 0 tags made it to final elites
    2. Breakthrough Moments (fitness jumps) - when fitness jumped, which tags changed
    3. Elite Tag Patterns (winner characteristics) - what tags do high performers share

    REQUIRES: Single-tag eras only (where single_tag = true)
    """
    return render_template('tag_story.html')


@app.route('/api/tag_story/survival/<era>')
def get_tag_survival(era):
    """
    Get Gen 0/immigrant tags that survived to final generation elites.

    Identifies which tags from generation 0 (initial population) or immigrants
    appear in the top 20% of the final generation. This reveals "founder effects"
    - whether initial random diversity or later immigrants drive final success.

    Args:
        era: Era identifier (must be single_tag=true era)

    Returns:
        JSON object with survival data per tag type:
        {
            "era": "framework-v3-token-claude-phylo-2",
            "tag_types": {
                "role": {
                    "variants": [
                        {
                            "tag_guid": "abc-123",
                            "text_snippet": "Expert semantic...",
                            "text_full": "Expert semantic compressor...",
                            "elite_count": 18,
                            "mean_fitness_in_elites": 0.755,
                            "origin": "initial"
                        }
                    ]
                }
            }
        }

    Error Handling:
        Returns 404 if era not found
        Returns 500 if database query fails
    """
    try:
        cb = get_db()

        # First, check if this era has single_tag data
        check_query = f"""
            SELECT single_tag
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generation_stats`
            WHERE era = '{era}'
            LIMIT 1
        """
        check_result = list(cb.cluster.query(check_query))
        if not check_result:
            return jsonify({"error": f"Era '{era}' not found"}), 404

        if not check_result[0].get('single_tag'):
            return jsonify({
                "error": f"Era '{era}' is not a single-tag era. Tag evolutionary story requires single-tag eras."
            }), 400

        # First, get max generation
        max_gen_query = f"""
            SELECT MAX(generation) as max_gen
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations`
            WHERE era = '{era}'
        """
        max_gen_result = list(cb.cluster.query(max_gen_query))
        if not max_gen_result or max_gen_result[0]['max_gen'] is None:
            return jsonify({"error": f"No generations found for era '{era}'"}), 404

        max_gen = max_gen_result[0]['max_gen']

        # Second, count prompts in final generation and calculate 20% threshold
        count_query = f"""
            SELECT COUNT(*) as final_gen_count
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations`
            WHERE era = '{era}' AND generation = {max_gen}
        """
        count_result = list(cb.cluster.query(count_query))
        final_count = count_result[0]['final_gen_count']
        threshold_count = round(final_count * 0.2)

        tag_types = ['role', 'compression_target', 'fidelity', 'constraints', 'output']
        tag_type_data = {}

        for tag_type in tag_types:
            tag_field = f'`{tag_type}`' if tag_type in ['role', 'output'] else tag_type

            query = f"""
                WITH elites AS (
                    SELECT p.*
                    FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
                    WHERE p.era = '{era}'
                      AND p.generation = {max_gen}
                    ORDER BY p.fitness DESC
                    LIMIT {threshold_count}
                )
                SELECT
                    e.{tag_field}.guid as tag_guid,
                    SUBSTR(MIN(e.{tag_field}.text), 0, 60) as text_snippet,
                    MIN(e.{tag_field}.text) as text_full,
                    COUNT(*) as elite_count,
                    AVG(e.fitness) as mean_fitness_in_elites,
                    MIN(e.{tag_field}.origin) as origin
                FROM elites e
                WHERE (e.{tag_field}.origin = 'initial' OR e.{tag_field}.origin = 'immigrant')
                GROUP BY e.{tag_field}.guid
                ORDER BY elite_count DESC, mean_fitness_in_elites DESC
            """

            results = cb.cluster.query(query)
            variants = [row for row in results]
            tag_type_data[tag_type] = {"variants": variants}

        return jsonify({
            "era": era,
            "tag_types": tag_type_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tag_story/breakthroughs/<era>')
def get_tag_breakthroughs(era):
    """
    Identify fitness breakthrough moments and which tags changed.

    Finds generations where max fitness jumped significantly, then compares
    the best prompt from generation N-1 with the best from generation N to
    identify which tags changed during the breakthrough.

    Query params:
        threshold (optional): Minimum fitness delta to consider a breakthrough (default: 0.001)

    Args:
        era: Era identifier (must be single_tag=true era)

    Returns:
        JSON object with breakthrough timeline:
        {
            "era": "framework-v3-token-claude-phylo-2",
            "threshold": 0.001,
            "breakthroughs": [
                {
                    "from_generation": 2,
                    "to_generation": 3,
                    "fitness_delta": 0.008,
                    "prev_fitness": 0.785,
                    "curr_fitness": 0.793,
                    "changes": {
                        "role": {"changed": false, "prev_guid": "abc", "curr_guid": "abc"},
                        "compression_target": {"changed": true, ...}
                    }
                }
            ]
        }

    Error Handling:
        Returns 404 if era not found
        Returns 500 if database query fails
    """
    try:
        cb = get_db()
        threshold = request.args.get('threshold', default=0.001, type=float)

        # Check single_tag era
        check_query = f"""
            SELECT single_tag
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generation_stats`
            WHERE era = '{era}'
            LIMIT 1
        """
        check_result = list(cb.cluster.query(check_query))
        if not check_result:
            return jsonify({"error": f"Era '{era}' not found"}), 404

        if not check_result[0].get('single_tag'):
            return jsonify({
                "error": f"Era '{era}' is not a single-tag era. Tag evolutionary story requires single-tag eras."
            }), 400

        # Step 1: Find fitness jumps
        jumps_query = f"""
            SELECT
                generation,
                max_fitness,
                LAG(max_fitness) OVER (ORDER BY generation) as prev_max_fitness,
                max_fitness - LAG(max_fitness) OVER (ORDER BY generation) as delta
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generation_stats`
            WHERE era = '{era}'
            ORDER BY generation
        """

        results = cb.cluster.query(jumps_query)
        jumps = [row for row in results if row.get('delta') and row['delta'] > threshold]

        breakthroughs = []

        # Step 2: For each jump, compare best prompts from N-1 and N
        for jump in jumps:
            gen = jump['generation']
            if gen == 0:
                continue  # Skip gen 0 (no previous generation)

            compare_query = f"""
                WITH prev_best AS (
                    SELECT p.*
                    FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
                    WHERE p.era = '{era}'
                      AND p.generation = {gen - 1}
                    ORDER BY p.fitness DESC
                    LIMIT 1
                ),
                curr_best AS (
                    SELECT p.*
                    FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
                    WHERE p.era = '{era}'
                      AND p.generation = {gen}
                    ORDER BY p.fitness DESC
                    LIMIT 1
                )
                SELECT
                    'prev' as context,
                    pb.fitness,
                    pb.`role`.guid as role_guid,
                    pb.`role`.text as role_text,
                    pb.compression_target.guid as comp_guid,
                    pb.compression_target.text as comp_text,
                    pb.fidelity.guid as fidelity_guid,
                    pb.fidelity.text as fidelity_text,
                    pb.constraints.guid as constraints_guid,
                    pb.constraints.text as constraints_text,
                    pb.`output`.guid as output_guid,
                    pb.`output`.text as output_text
                FROM prev_best pb
                UNION ALL
                SELECT
                    'curr' as context,
                    cb.fitness,
                    cb.`role`.guid as role_guid,
                    cb.`role`.text as role_text,
                    cb.compression_target.guid as comp_guid,
                    cb.compression_target.text as comp_text,
                    cb.fidelity.guid as fidelity_guid,
                    cb.fidelity.text as fidelity_text,
                    cb.constraints.guid as constraints_guid,
                    cb.constraints.text as constraints_text,
                    cb.`output`.guid as output_guid,
                    cb.`output`.text as output_text
                FROM curr_best cb
            """

            compare_results = list(cb.cluster.query(compare_query))
            if len(compare_results) != 2:
                continue

            prev = compare_results[0] if compare_results[0]['context'] == 'prev' else compare_results[1]
            curr = compare_results[1] if compare_results[1]['context'] == 'curr' else compare_results[0]

            tag_types = ['role', 'compression_target', 'fidelity', 'constraints', 'output']
            changes = {}

            for tag_type in tag_types:
                prev_guid = prev.get(f'{tag_type}_guid' if tag_type != 'compression_target' else 'comp_guid')
                curr_guid = curr.get(f'{tag_type}_guid' if tag_type != 'compression_target' else 'comp_guid')
                prev_text = prev.get(f'{tag_type}_text' if tag_type != 'compression_target' else 'comp_text')
                curr_text = curr.get(f'{tag_type}_text' if tag_type != 'compression_target' else 'comp_text')

                changes[tag_type] = {
                    "changed": prev_guid != curr_guid,
                    "prev_guid": prev_guid,
                    "curr_guid": curr_guid,
                    "prev_text": prev_text,
                    "curr_text": curr_text
                }

            breakthroughs.append({
                "from_generation": gen - 1,
                "to_generation": gen,
                "fitness_delta": jump['delta'],
                "prev_fitness": jump['prev_max_fitness'],
                "curr_fitness": jump['max_fitness'],
                "changes": changes
            })

        return jsonify({
            "era": era,
            "threshold": threshold,
            "breakthroughs": breakthroughs
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tag_story/elite_patterns/<era>')
def get_elite_patterns(era):
    """
    Analyze which tags appear more frequently in elites vs regular prompts.

    Calculates enrichment ratios for each tag variant across all generations.
    Enrichment ratio > 1.0 means the tag appears MORE in elites than expected.

    Args:
        era: Era identifier (must be single_tag=true era)

    Returns:
        JSON object with enrichment data per tag type:
        {
            "era": "framework-v3-token-claude-phylo-2",
            "tag_types": {
                "role": {
                    "variants": [
                        {
                            "tag_guid": "abc-123",
                            "text_snippet": "Expert semantic...",
                            "text_full": "...",
                            "elite_count": 180,
                            "regular_count": 20,
                            "total_count": 200,
                            "elite_frequency": 0.90,
                            "enrichment_ratio": 4.5,
                            "mean_fitness": 0.755
                        }
                    ]
                }
            }
        }

    Error Handling:
        Returns 404 if era not found
        Returns 500 if database query fails
    """
    try:
        cb = get_db()

        # Check single_tag era
        check_query = f"""
            SELECT single_tag
            FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generation_stats`
            WHERE era = '{era}'
            LIMIT 1
        """
        check_result = list(cb.cluster.query(check_query))
        if not check_result:
            return jsonify({"error": f"Era '{era}' not found"}), 404

        if not check_result[0].get('single_tag'):
            return jsonify({
                "error": f"Era '{era}' is not a single-tag era. Tag evolutionary story requires single-tag eras."
            }), 400

        tag_types = ['role', 'compression_target', 'fidelity', 'constraints', 'output']
        tag_type_data = {}

        for tag_type in tag_types:
            tag_field = f'`{tag_type}`' if tag_type in ['role', 'output'] else tag_type

            query = f"""
                WITH fitness_percentiles AS (
                    SELECT
                        p.*,
                        PERCENT_RANK() OVER (PARTITION BY p.generation ORDER BY p.fitness) as percentile
                    FROM `{cb.bucket_name}`.`{cb.scope_name}`.`generations` p
                    WHERE p.era = '{era}'
                ),
                tag_frequencies AS (
                    SELECT
                        fp.{tag_field}.guid as tag_guid,
                        MIN(fp.{tag_field}.text) as text_full,
                        SUBSTR(MIN(fp.{tag_field}.text), 0, 60) as text_snippet,
                        COUNT(DISTINCT CASE WHEN fp.percentile >= 0.80 THEN fp.prompt_id END) as elite_count,
                        COUNT(DISTINCT CASE WHEN fp.percentile < 0.80 THEN fp.prompt_id END) as regular_count,
                        COUNT(DISTINCT fp.prompt_id) as total_count,
                        AVG(fp.fitness) as mean_fitness
                    FROM fitness_percentiles fp
                    GROUP BY fp.{tag_field}.guid
                    HAVING COUNT(DISTINCT CASE WHEN fp.percentile >= 0.80 THEN fp.prompt_id END) > 0
                )
                SELECT
                    tag_guid,
                    text_snippet,
                    text_full,
                    elite_count,
                    regular_count,
                    total_count,
                    mean_fitness,
                    elite_count / NULLIF(total_count, 0) as elite_frequency,
                    (elite_count / NULLIF(total_count, 0)) / 0.20 as enrichment_ratio
                FROM tag_frequencies
                ORDER BY enrichment_ratio DESC, elite_count DESC
                LIMIT 15
            """

            results = cb.cluster.query(query)
            variants = [row for row in results]
            tag_type_data[tag_type] = {"variants": variants}

        return jsonify({
            "era": era,
            "tag_types": tag_type_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("\n" + "="*60)
    print("GENETIC ALGORITHM VISUALIZATION DASHBOARD")
    print("="*60)
    print("Starting Flask server...")
    print("Dashboard URL: http://localhost:8080")
    print("="*60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=8080)
