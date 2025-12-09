/**
 * Phylogenetic Tree Visualization
 *
 * Force-directed graph showing evolutionary lineage of prompts with:
 * - Nodes: Individual prompts (colored by type, sized by fitness)
 * - Edges: Parent → child relationships (colored by fitness change)
 * - Rich tooltips: Full prompt data on hover
 * - Details panel: Complete prompt info on click
 *
 * Used by: dashboard.html (called on era selection)
 * Requires: D3.js v7, prompts data from /api/tree/<era>
 */

function renderPhyloTree(prompts) {
    // Clear any existing tree
    d3.select('#phylo-tree').selectAll('*').remove();

    // Container dimensions
    const container = document.getElementById('phylo-tree');
    const width = container.clientWidth;
    const height = 600;

    // Color scheme by prompt type (matches existing charts)
    const typeColors = {
        'initial': '#10AC84',      // Green
        'mutation': '#EE5A6F',     // Red
        'crossover': '#F79F1F',    // Orange
        'immigrant': '#9B59B6'     // Purple
    };

    // Fitness scale for node size (5-20px radius)
    const fitnessExtent = d3.extent(prompts, d => d.fitness || 0);
    const radiusScale = d3.scaleLinear()
        .domain(fitnessExtent)
        .range([5, 20]);

    // Build nodes array (one per prompt)
    const nodes = prompts.map(p => ({
        id: p.prompt_id,
        generation: p.generation,
        type: p.type,
        fitness: p.fitness || 0,
        compression_ratio: p.compression_ratio,
        quality_score_avg: p.quality_score_avg,
        model_used: p.model_used,
        parents: p.parents || [],

        // Tag data for tooltip/details
        tags: {
            role: {
                guid: p.role_guid,
                text: p.role_text,
                origin: p.role_origin,
                source: p.role_source
            },
            compression_target: {
                guid: p.comp_guid,
                text: p.comp_text,
                origin: p.comp_origin,
                source: p.comp_source
            },
            fidelity: {
                guid: p.fidelity_guid,
                text: p.fidelity_text,
                origin: p.fidelity_origin,
                source: p.fidelity_source
            },
            constraints: {
                guid: p.constraints_guid,
                text: p.constraints_text,
                origin: p.constraints_origin,
                source: p.constraints_source
            },
            output: {
                guid: p.output_guid,
                text: p.output_text,
                origin: p.output_origin,
                source: p.output_source
            }
        }
    }));

    // Build edges array (parent → child links)
    const edges = [];
    const nodeMap = new Map(nodes.map(n => [n.id, n]));

    nodes.forEach(child => {
        if (child.parents && child.parents.length > 0) {
            child.parents.forEach(parentId => {
                const parent = nodeMap.get(parentId);
                if (parent) {
                    const fitnessChange = child.fitness - parent.fitness;
                    edges.push({
                        source: parentId,
                        target: child.id,
                        fitnessChange: fitnessChange
                    });
                }
            });
        }
    });

    // Edge color by fitness change
    const edgeColor = (fitnessChange) => {
        if (fitnessChange > 0.5) return '#2ECC71';  // Green (improved)
        if (fitnessChange < -0.5) return '#E74C3C'; // Red (degraded)
        return '#95A5A6';  // Gray (neutral)
    };

    // Create SVG
    const svg = d3.select('#phylo-tree')
        .append('svg')
        .attr('width', width)
        .attr('height', height);

    // Add zoom behavior
    const g = svg.append('g');
    const zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });
    svg.call(zoom);

    // Create force simulation
    const simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(edges)
            .id(d => d.id)
            .distance(100))
        .force('charge', d3.forceManyBody()
            .strength(-300))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide()
            .radius(d => radiusScale(d.fitness) + 5));

    // Draw edges
    const link = g.append('g')
        .selectAll('line')
        .data(edges)
        .enter().append('line')
        .attr('stroke', d => edgeColor(d.fitnessChange))
        .attr('stroke-width', 2)
        .attr('stroke-opacity', 0.6)
        .style('cursor', 'pointer');

    // Draw nodes
    const node = g.append('g')
        .selectAll('circle')
        .data(nodes)
        .enter().append('circle')
        .attr('r', d => radiusScale(d.fitness))
        .attr('fill', d => typeColors[d.type] || '#95A5A6')
        .attr('stroke', '#fff')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .call(d3.drag()
            .on('start', dragStarted)
            .on('drag', dragged)
            .on('end', dragEnded));

    // Add generation labels
    const label = g.append('g')
        .selectAll('text')
        .data(nodes)
        .enter().append('text')
        .text(d => `G${d.generation}`)
        .attr('font-size', '10px')
        .attr('font-family', 'monospace')
        .attr('fill', '#2C3E50')
        .attr('text-anchor', 'middle')
        .attr('dy', 4)
        .style('pointer-events', 'none');

    // Tooltip for rich hover info
    const tooltip = d3.select('body')
        .append('div')
        .attr('class', 'phylo-tooltip')
        .style('position', 'absolute')
        .style('visibility', 'hidden')
        .style('background', 'rgba(0, 0, 0, 0.9)')
        .style('color', '#fff')
        .style('padding', '12px')
        .style('border-radius', '4px')
        .style('font-size', '12px')
        .style('font-family', 'monospace')
        .style('max-width', '400px')
        .style('z-index', '1000')
        .style('pointer-events', 'none');

    // Edge hover: Show fitness change
    link.on('mouseover', (event, d) => {
        const parent = nodeMap.get(d.source.id || d.source);
        const child = nodeMap.get(d.target.id || d.target);
        const change = d.fitnessChange;
        const arrow = change > 0 ? '↑' : change < 0 ? '↓' : '→';
        const color = change > 0 ? '#2ECC71' : change < 0 ? '#E74C3C' : '#95A5A6';

        tooltip.html(`
            <strong>Parent → Child</strong><br>
            ${parent.id.substring(0, 12)}... → ${child.id.substring(0, 12)}...<br>
            <strong>Fitness Change:</strong> <span style="color: ${color};">${arrow} ${change >= 0 ? '+' : ''}${change.toFixed(2)}</span><br>
            Parent fitness: ${parent.fitness.toFixed(2)}<br>
            Child fitness: ${child.fitness.toFixed(2)}
        `)
        .style('visibility', 'visible');

        // Highlight edge
        d3.select(event.target)
            .attr('stroke-width', 4)
            .attr('stroke-opacity', 1);
    })
    .on('mousemove', (event) => {
        tooltip
            .style('top', (event.pageY - 10) + 'px')
            .style('left', (event.pageX + 10) + 'px');
    })
    .on('mouseout', (event) => {
        tooltip.style('visibility', 'hidden');

        // Restore edge appearance
        d3.select(event.target)
            .attr('stroke-width', 2)
            .attr('stroke-opacity', 0.6);
    });

    // Node hover: Show rich tooltip
    node.on('mouseover', (event, d) => {
        const parentIds = d.parents.length > 0
            ? d.parents.map(p => p.substring(0, 8)).join(', ')
            : 'None';

        tooltip.html(`
            <strong>Prompt:</strong> ${d.id.substring(0, 12)}...<br>
            <strong>Generation:</strong> ${d.generation} | <strong>Type:</strong> ${d.type}<br>
            <strong>Fitness:</strong> ${d.fitness.toFixed(2)}<br>
            <strong>Compression:</strong> ${d.compression_ratio.toFixed(2)}x | <strong>Quality:</strong> ${d.quality_score_avg.toFixed(2)}/10<br>
            <strong>Model:</strong> ${d.model_used}<br>
            <strong>Parents:</strong> ${parentIds}<br>
            <hr style="border-color: #555; margin: 8px 0;">
            <strong>Tag Origins:</strong><br>
            &nbsp;&nbsp;Role: ${d.tags.role.origin}<br>
            &nbsp;&nbsp;Comp Target: ${d.tags.compression_target.origin}<br>
            &nbsp;&nbsp;Fidelity: ${d.tags.fidelity.origin}<br>
            &nbsp;&nbsp;Constraints: ${d.tags.constraints.origin}<br>
            &nbsp;&nbsp;Output: ${d.tags.output.origin}
        `)
        .style('visibility', 'visible');
    })
    .on('mousemove', (event) => {
        tooltip
            .style('top', (event.pageY - 10) + 'px')
            .style('left', (event.pageX + 10) + 'px');
    })
    .on('mouseout', () => {
        tooltip.style('visibility', 'hidden');
    });

    // Click: Show details panel
    node.on('click', (event, d) => {
        showDetailsPanel(d);
    });

    // Update positions on simulation tick
    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node
            .attr('cx', d => d.x)
            .attr('cy', d => d.y);

        label
            .attr('x', d => d.x)
            .attr('y', d => d.y);
    });

    // Drag handlers
    function dragStarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }

    function dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }

    function dragEnded(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }
}

/**
 * Show details panel with complete prompt information
 */
function showDetailsPanel(promptData) {
    const panel = document.getElementById('details-panel');
    const content = document.getElementById('details-content');

    // Build parent links
    const parentLinks = promptData.parents.length > 0
        ? promptData.parents.map(p => `<code>${p.substring(0, 12)}...</code>`).join(', ')
        : '<em>None (Gen 0 or Immigrant)</em>';

    // Build tag details table
    const tagRows = Object.entries(promptData.tags).map(([tagType, tag]) => `
        <tr>
            <td><strong>${tagType.replace('_', ' ')}</strong></td>
            <td><code>${tag.guid.substring(0, 8)}...</code></td>
            <td><span class="badge badge-${tag.origin}">${tag.origin}</span></td>
            <td><span class="badge badge-${tag.source}">${tag.source}</span></td>
            <td style="max-width: 300px; font-size: 11px;">${tag.text}</td>
        </tr>
    `).join('');

    content.innerHTML = `
        <h3>Prompt Details</h3>

        <div class="detail-section">
            <h4>Identity</h4>
            <p><strong>ID:</strong> <code>${promptData.id}</code></p>
            <p><strong>Generation:</strong> ${promptData.generation}</p>
            <p><strong>Type:</strong> <span class="badge badge-${promptData.type}">${promptData.type}</span></p>
            <p><strong>Model:</strong> ${promptData.model_used}</p>
            <p><strong>Parents:</strong> ${parentLinks}</p>
        </div>

        <div class="detail-section">
            <h4>Performance</h4>
            <p><strong>Fitness:</strong> ${promptData.fitness.toFixed(3)}</p>
            <p><strong>Compression Ratio:</strong> ${promptData.compression_ratio.toFixed(2)}x</p>
            <p><strong>Quality Score:</strong> ${promptData.quality_score_avg.toFixed(2)} / 10</p>
        </div>

        <div class="detail-section">
            <h4>Tags</h4>
            <table class="tag-table">
                <thead>
                    <tr>
                        <th>Tag Type</th>
                        <th>GUID</th>
                        <th>Origin</th>
                        <th>Source</th>
                        <th>Text</th>
                    </tr>
                </thead>
                <tbody>
                    ${tagRows}
                </tbody>
            </table>
        </div>
    `;

    // Show panel
    panel.classList.add('open');
}

/**
 * Close details panel
 */
function closeDetailsPanel() {
    const panel = document.getElementById('details-panel');
    panel.classList.remove('open');
}
