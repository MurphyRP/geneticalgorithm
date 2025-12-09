/**
 * Lineage Sankey Visualization
 *
 * Interactive Sankey diagram showing evolutionary lineage of prompts:
 * - Top N filtering (show only top performers and their ancestry)
 * - Single node drill-down (click to explore specific lineage)
 * - Inheritance proportion flows (approximated by counting tag matches)
 * - Fitness delta colors (red = decline, grey = neutral, green = improvement)
 * - Navigation controls (Back, Reset, breadcrumbs)
 *
 * WHY: Provides focused view of successful lineages, complementing the full phylo tree.
 *      Enables tracing high-fitness prompts back to their ancestral origins.
 *
 * USED BY: lineage.html (dedicated full-screen page)
 * REQUIRES: D3.js v7, d3-sankey plugin, tree data from /api/tree/<era>
 * RELATED: phylo_tree.js (shows full population), fitness_chart.js (shows trends)
 */

// Main rendering function
function renderLineageSankey(treeData, view) {
    // Clear existing visualization AND tooltips
    d3.select('#sankey-container').selectAll('svg').remove();
    d3.selectAll('.sankey-tooltip').remove();

    // NOTE: Data is now pre-cleaned by SQL query using composite keys (prompt_id-gen-N)
    // This ensures each generation instance is unique, eliminating circular references
    console.log(`Processing ${treeData.length} prompts with composite keys`);

    // Filter data based on view type
    let filteredData;
    if (view.type === 'topN') {
        filteredData = filterToTopN(treeData, view.topN);
    } else if (view.type === 'singleNode') {
        filteredData = filterToSingleLineage(treeData, view.promptId);
    } else {
        console.error('Unknown view type:', view.type);
        return;
    }

    // Update info display
    document.getElementById('node-count').textContent = `${filteredData.nodes.length} nodes`;
    document.getElementById('flow-count').textContent = `${filteredData.links.length} flows`;

    // Build and render Sankey
    buildSankeyLayout(filteredData);
}

/**
 * Debug logger for lineage trace results
 *
 * Outputs detailed information about the traced lineage to console:
 * - Which prompt we started from
 * - Nodes found at each generation
 * - Parent relationships for each node
 * - Validation results (Gen 0 reached, etc.)
 *
 * WHY: Research code must be debuggable. This enables verification that
 *      the trace algorithm is working correctly.
 */
function logLineageTrace(startPromptId, nodesByGeneration, allNodes) {
    console.log('\n=== LINEAGE TRACE DEBUG ===');

    // Find the starting prompt
    const startPrompt = allNodes.find(p => p.prompt_id === startPromptId);
    if (startPrompt) {
        console.log(`Starting from: ${startPromptId.substring(0, 12)}... (Gen ${startPrompt.generation}, fitness: ${(startPrompt.fitness || 0).toFixed(2)})`);
    } else {
        console.log(`Starting from: ${startPromptId.substring(0, 12)}...`);
    }

    // Get sorted generation numbers
    const generations = Object.keys(nodesByGeneration)
        .map(g => parseInt(g))
        .sort((a, b) => b - a);  // Descending order (newest first)

    // Log each generation
    generations.forEach(gen => {
        const nodes = nodesByGeneration[gen];
        console.log(`Gen ${gen}: ${nodes.length} node(s)`);

        nodes.forEach(node => {
            const parentIds = node.parents && Array.isArray(node.parents)
                ? node.parents.map(id => id.substring(0, 8)).join(', ')
                : (node.parents === null ? '[]' : 'undefined');

            console.log(`  - ${node.prompt_id.substring(0, 12)}... (fitness: ${(node.fitness || 0).toFixed(2)}, type: ${node.type}, parents: [${parentIds}])`);
        });
    });

    // Validation checks
    console.log('\n=== VALIDATION ===');
    console.log(`✓ Generation 0 reached: ${nodesByGeneration.hasOwnProperty(0) ? 'YES' : 'NO ❌'}`);
    console.log(`✓ Total generations: ${generations.length}`);
    console.log(`✓ Generation range: ${Math.min(...generations)} to ${Math.max(...generations)}`);
    console.log(`✓ Total nodes traced: ${allNodes.length}`);

    // Check for broken chains (nodes at Gen > 0 with no parents in the trace)
    let brokenChains = 0;
    generations.forEach(gen => {
        if (gen === 0) return;  // Skip Gen 0

        const nodes = nodesByGeneration[gen];
        nodes.forEach(node => {
            if (!node.parents || node.parents.length === 0) {
                // This is an immigrant - OK to have no parents
                if (node.type !== 'immigrant' && node.type !== 'initial') {
                    console.log(`⚠️  Warning: ${node.prompt_id.substring(0, 12)}... at Gen ${gen} has no parents but is type '${node.type}'`);
                    brokenChains++;
                }
            }
        });
    });

    if (brokenChains > 0) {
        console.log(`❌ Found ${brokenChains} broken chain(s)`);
    } else {
        console.log('✓ No broken chains detected');
    }

    console.log('=== END TRACE ===\n');
}

/**
 * Filter to Top N prompts and their complete ancestry
 *
 * ALGORITHM:
 * 1. Find top N prompts from final generation by fitness
 * 2. Trace backward through parents until reaching Generation 0
 * 3. Validate that Gen 0 was reached
 * 4. Build nodes and links from traced lineage
 *
 * CRITICAL: Must trace ALL THE WAY to Generation 0. If Gen 0 is not
 * reached, the data is broken or the algorithm failed.
 */
function filterToTopN(treeData, topN) {
    // Step 1: Get final generation
    const maxGeneration = Math.max(...treeData.map(p => p.generation));
    const finalGenPrompts = treeData.filter(p => p.generation === maxGeneration);

    // Step 2: Sort by fitness and take top N
    const topPrompts = finalGenPrompts
        .sort((a, b) => (b.fitness || 0) - (a.fitness || 0))
        .slice(0, topN);

    console.log(`\n=== FILTERING TO TOP ${topN} ===`);
    console.log(`Max generation in data: ${maxGeneration}`);
    console.log(`Final generation has ${finalGenPrompts.length} prompts`);
    console.log(`\nTop ${topN} prompts from Gen ${maxGeneration}:`);
    topPrompts.forEach((p, i) => {
        console.log(`  ${i+1}. ${p.prompt_id.substring(0, 12)}... (fitness: ${(p.fitness || 0).toFixed(2)}, type: ${p.type}, parents: ${p.parents ? `[${p.parents.map(id => id.substring(0, 8)).join(', ')}]` : 'null'})`);
    });

    // Step 3: Build node map for quick lookup
    const nodeMap = new Map(treeData.map(p => [p.prompt_id, p]));

    console.log(`\nTotal prompts in treeData: ${treeData.length}`);

    // Show generation distribution in raw data
    const genCounts = {};
    treeData.forEach(p => {
        genCounts[p.generation] = (genCounts[p.generation] || 0) + 1;
    });
    console.log(`Generation distribution in treeData:`, genCounts);

    // Step 4: Backward trace using breadth-first search
    console.log(`\n=== BACKWARD TRACE (BFS) ===`);
    const includedNodeIds = new Set();
    const toExplore = [...topPrompts.map(p => p.prompt_id)];
    const visited = new Set();  // Prevent infinite loops

    let iterationCount = 0;
    while (toExplore.length > 0) {
        iterationCount++;
        const promptId = toExplore.shift();  // BFS: use shift() not pop()

        // Skip if already visited
        if (visited.has(promptId)) {
            console.log(`  [${iterationCount}] Skip ${promptId.substring(0, 8)}... (already visited)`);
            continue;
        }
        visited.add(promptId);

        // Add to included nodes
        includedNodeIds.add(promptId);

        const prompt = nodeMap.get(promptId);
        if (!prompt) {
            console.warn(`  [${iterationCount}] ⚠️  Prompt ${promptId.substring(0, 12)}... not found in treeData`);
            continue;
        }

        console.log(`  [${iterationCount}] Exploring ${prompt.prompt_id.substring(0, 8)}... (Gen ${prompt.generation}, type: ${prompt.type})`);

        // If prompt has parents, add them to exploration queue
        // Handle both null and empty array cases
        if (prompt.parents && Array.isArray(prompt.parents) && prompt.parents.length > 0) {
            console.log(`    → Has ${prompt.parents.length} parent(s): ${prompt.parents.map(id => id.substring(0, 8)).join(', ')}`);
            prompt.parents.forEach(parentId => {
                if (!visited.has(parentId)) {
                    toExplore.push(parentId);
                    console.log(`      + Added ${parentId.substring(0, 8)}... to queue`);
                } else {
                    console.log(`      - Skip ${parentId.substring(0, 8)}... (already visited)`);
                }
            });
        } else {
            console.log(`    → No parents (Gen 0 or immigrant)`);
        }
        // If parents is null or empty, this is Gen 0 or immigrant - stop tracing this branch
    }

    console.log(`\nBFS complete: ${iterationCount} iterations, ${includedNodeIds.size} nodes included\n`);

    // Step 5: Filter to included nodes
    const nodes = treeData.filter(p => includedNodeIds.has(p.prompt_id));

    // Step 6: Organize nodes by generation for validation
    const nodesByGeneration = {};
    nodes.forEach(node => {
        if (!nodesByGeneration[node.generation]) {
            nodesByGeneration[node.generation] = [];
        }
        nodesByGeneration[node.generation].push(node);
    });

    // Step 7: Validation - CRITICAL
    if (!nodesByGeneration.hasOwnProperty(0)) {
        console.error('❌ TRACE FAILED: Generation 0 not reached!');
        console.error('This means the lineage trace did not complete properly.');
        console.error('Possible causes:');
        console.error('  1. Data is broken (parents pointing to non-existent prompts)');
        console.error('  2. All lineages are from immigrants (no Gen 0 ancestry)');
        console.error('  3. Algorithm bug');

        // Still show what we found for debugging
        logLineageTrace(topPrompts[0].prompt_id, nodesByGeneration, nodes);

        // For now, continue rendering but log the error
        // In production, you might want to show an error message to user
    } else {
        // Success - log the trace
        logLineageTrace(topPrompts[0].prompt_id, nodesByGeneration, nodes);
    }

    // Step 7b: Data integrity check - immigrants at Gen > 0 (should be impossible)
    Object.keys(nodesByGeneration).forEach(gen => {
        const genNum = parseInt(gen);
        if (genNum > 0) {
            const immigrants = nodesByGeneration[gen].filter(p => p.type === 'immigrant');
            if (immigrants.length > 0) {
                console.error(`\n❌ DATA INTEGRITY ERROR: Found ${immigrants.length} immigrant(s) at Gen ${gen}`);
                console.error('Immigrants should ONLY exist at Generation 0!');
                immigrants.forEach(p => {
                    console.error(`  - ${p.prompt_id.substring(0, 12)}... (type: ${p.type}, parents: ${p.parents})`);
                });
                console.error('This indicates corrupt data in the database.\n');
            }
        }
    });

    // Step 8: Build edges (links) between included nodes
    const links = [];
    nodes.forEach(child => {
        // Handle null and empty array cases
        if (child.parents && Array.isArray(child.parents) && child.parents.length > 0) {
            child.parents.forEach(parentId => {
                const parent = nodeMap.get(parentId);
                if (parent && includedNodeIds.has(parentId)) {
                    const proportion = calculateInheritanceProportion(child, parent, nodeMap);
                    const fitnessDelta = (child.fitness || 0) - (parent.fitness || 0);

                    links.push({
                        source: parentId,
                        target: child.prompt_id,
                        value: proportion,  // Flow width (0.0 to 1.0)
                        fitnessDelta: fitnessDelta,
                        parent: parent,
                        child: child
                    });
                }
            });
        }
    });

    console.log(`Trace complete: ${nodes.length} nodes, ${links.length} links\n`);

    return { nodes, links };
}

/**
 * Filter to single lineage (all ancestors + all descendants)
 *
 * ALGORITHM:
 * 1. Start from selected prompt
 * 2. Trace backward through parents to Generation 0
 * 3. Trace forward through children to final generation
 * 4. Validate that Gen 0 was reached (if not an immigrant lineage)
 * 5. Build nodes and links from traced lineage
 */
function filterToSingleLineage(treeData, selectedPromptId) {
    const nodeMap = new Map(treeData.map(p => [p.prompt_id, p]));
    const includedNodeIds = new Set([selectedPromptId]);
    const visited = new Set();

    // PART 1: Get all ancestors (walk up via parents)
    const ancestorsToExplore = [selectedPromptId];

    while (ancestorsToExplore.length > 0) {
        const promptId = ancestorsToExplore.shift();  // BFS

        if (visited.has(promptId)) continue;
        visited.add(promptId);

        const prompt = nodeMap.get(promptId);
        if (!prompt) {
            console.warn(`⚠️  Prompt ${promptId.substring(0, 12)}... not found in treeData`);
            continue;
        }

        // If prompt has parents, add them to exploration
        if (prompt.parents && Array.isArray(prompt.parents) && prompt.parents.length > 0) {
            prompt.parents.forEach(parentId => {
                if (!visited.has(parentId)) {
                    includedNodeIds.add(parentId);
                    ancestorsToExplore.push(parentId);
                }
            });
        }
    }

    // PART 2: Build reverse index (children by parent)
    const childrenByParent = new Map();
    treeData.forEach(prompt => {
        if (prompt.parents && Array.isArray(prompt.parents) && prompt.parents.length > 0) {
            prompt.parents.forEach(parentId => {
                if (!childrenByParent.has(parentId)) {
                    childrenByParent.set(parentId, []);
                }
                childrenByParent.get(parentId).push(prompt.prompt_id);
            });
        }
    });

    // PART 3: Get all descendants (walk down via children)
    const descendantsToExplore = [selectedPromptId];
    const visitedDescendants = new Set();

    while (descendantsToExplore.length > 0) {
        const promptId = descendantsToExplore.shift();  // BFS

        if (visitedDescendants.has(promptId)) continue;
        visitedDescendants.add(promptId);

        const children = childrenByParent.get(promptId) || [];

        children.forEach(childId => {
            if (!visitedDescendants.has(childId)) {
                includedNodeIds.add(childId);
                descendantsToExplore.push(childId);
            }
        });
    }

    // Filter to included nodes
    const nodes = treeData.filter(p => includedNodeIds.has(p.prompt_id));

    // Organize nodes by generation for validation
    const nodesByGeneration = {};
    nodes.forEach(node => {
        if (!nodesByGeneration[node.generation]) {
            nodesByGeneration[node.generation] = [];
        }
        nodesByGeneration[node.generation].push(node);
    });

    // Validation
    const selectedPrompt = nodeMap.get(selectedPromptId);
    if (selectedPrompt && selectedPrompt.generation > 0 && !nodesByGeneration.hasOwnProperty(0)) {
        // Only warn if selected prompt is not Gen 0 and we didn't reach Gen 0
        // This is OK if the selected prompt is an immigrant lineage
        if (selectedPrompt.type !== 'immigrant') {
            console.warn('⚠️  Generation 0 not reached - this may be an immigrant lineage');
        }
    }

    // Log the trace
    logLineageTrace(selectedPromptId, nodesByGeneration, nodes);

    // Build edges
    const links = [];
    nodes.forEach(child => {
        if (child.parents && Array.isArray(child.parents) && child.parents.length > 0) {
            child.parents.forEach(parentId => {
                const parent = nodeMap.get(parentId);
                if (parent && includedNodeIds.has(parentId)) {
                    const proportion = calculateInheritanceProportion(child, parent, nodeMap);
                    const fitnessDelta = (child.fitness || 0) - (parent.fitness || 0);

                    links.push({
                        source: parentId,
                        target: child.prompt_id,
                        value: proportion,
                        fitnessDelta: fitnessDelta,
                        parent: parent,
                        child: child
                    });
                }
            });
        }
    });

    console.log(`Single lineage trace complete: ${nodes.length} nodes, ${links.length} links\n`);

    return { nodes, links };
}

/**
 * Calculate inheritance proportion for a parent→child edge
 *
 * Approximation method: Count how many of the 5 tags match the parent's tag GUIDs
 * via the child's parent_tag_guid field.
 *
 * - Mutation (1 parent): 100% from parent
 * - Crossover (2 parents): Proportion = matching_tags / 5.0
 * - Initial/Immigrant: 0% (no parent)
 *
 * LIMITATION: This is an approximation. The actual crossover operator may not have
 * split tags exactly as implied by parent_tag_guid matches.
 */
function calculateInheritanceProportion(child, parent, nodeMap) {
    if (!child.parents || child.parents.length === 0) {
        return 0;  // Initial or immigrant
    }

    if (child.parents.length === 1) {
        return 1.0;  // Mutation: 100% from single parent
    }

    // Crossover: count matching tag parent_guids
    const tagTypes = ['role', 'comp', 'fidelity', 'constraints', 'output'];
    let matches = 0;

    tagTypes.forEach(tagType => {
        const childParentGuid = child[`${tagType}_parent_guid`];
        const parentGuid = parent[`${tagType}_guid`];

        if (childParentGuid && parentGuid && childParentGuid === parentGuid) {
            matches++;
        }
    });

    return matches / 5.0;  // Proportion 0.0 to 1.0
}

/**
 * Get fitness delta color
 */
function getFitnessDeltaColor(delta) {
    if (delta < -0.1) return '#DC2626';  // Red (decline)
    if (delta > 0.1) return '#16A34A';   // Green (improvement)
    return '#9CA3AF';  // Grey (neutral)
}

/**
 * Get color for tag source type
 */
function getSourceColor(source) {
    const colors = {
        'initial': '#10AC84',    // Green - original
        'mutation': '#EE5A6F',   // Red - mutated
        'crossover': '#F79F1F',  // Orange - crossed over
        'immigrant': '#9B59B6'   // Purple - fresh immigrant
    };
    return colors[source] || '#95A5A6';
}

/**
 * Compare tags between parent and child to show what changed
 */
function getTagChangeSummary(parent, child) {
    const tagTypes = [
        { name: 'Role', childGuid: child.role_guid, parentGuid: parent.role_guid, source: child.role_source },
        { name: 'Comp', childGuid: child.comp_guid, parentGuid: parent.comp_guid, source: child.comp_source },
        { name: 'Fidelity', childGuid: child.fidelity_guid, parentGuid: parent.fidelity_guid, source: child.fidelity_source },
        { name: 'Constraints', childGuid: child.constraints_guid, parentGuid: parent.constraints_guid, source: child.constraints_source },
        { name: 'Output', childGuid: child.output_guid, parentGuid: parent.output_guid, source: child.output_source }
    ];

    let inherited = [];
    let changed = [];

    tagTypes.forEach(tag => {
        if (tag.childGuid === tag.parentGuid) {
            inherited.push(tag.name);
        } else {
            changed.push(`${tag.name} (${tag.source})`);
        }
    });

    return { inherited, changed };
}

/**
 * Build and render D3 Sankey layout
 */
function buildSankeyLayout(filteredData) {
    const container = document.getElementById('sankey-container');
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Prepare nodes for D3 sankey (needs {name: ...} structure)
    // Add fitness as a property that will influence node height
    const sankeyNodes = filteredData.nodes.map(p => ({
        name: p.prompt_id,
        promptData: p,
        fitness: p.fitness || 0
    }));

    // Prepare links for D3 sankey
    // Flow width based on absolute fitness delta (thicker = bigger impact)
    // Minimum width of 2 for visibility, scale delta for reasonable widths
    const sankeyLinks = filteredData.links.map(link => {
        const absDelta = Math.abs(link.fitnessDelta);
        // Scale: small delta (0-5) = thin, large delta (50+) = thick
        // Use log scale to handle wide range of fitness changes
        const scaledValue = Math.max(2, Math.log10(absDelta + 1) * 10);

        return {
            source: link.source,
            target: link.target,
            value: scaledValue,
            fitnessDelta: link.fitnessDelta,
            parent: link.parent,
            child: link.child
        };
    });

    // CRITICAL FIX: Calculate X positions based on generation numbers
    // D3 Sankey auto-positions nodes, which breaks generational layout
    // We must manually set X coordinates based on generation

    // Step 1: Find generation range
    const generations = new Set(filteredData.nodes.map(p => p.generation));
    const minGen = Math.min(...generations);
    const maxGen = Math.max(...generations);

    console.log(`\n=== SANKEY LAYOUT ===`);
    console.log(`Generation range: ${minGen} to ${maxGen}`);

    // Step 2: Calculate X position for each generation
    const xPadding = 100;  // Left/right margins
    const nodeWidth = 15;  // Must match sankey.nodeWidth()
    const availableWidth = width - (2 * xPadding) - nodeWidth;
    const generationSpacing = maxGen > 0 ? availableWidth / maxGen : 0;

    console.log(`Width: ${width}, Available: ${availableWidth}, Spacing: ${generationSpacing.toFixed(1)}`);

    // Step 3: Pre-assign X positions to each node based on generation
    sankeyNodes.forEach(node => {
        const gen = node.promptData.generation;
        node.x0 = xPadding + (gen * generationSpacing);
        node.x1 = node.x0 + nodeWidth;
    });

    // Step 4: Create Sankey with fixed X positions
    const sankey = d3.sankey()
        .nodeId(d => d.name)
        .nodeWidth(nodeWidth)
        .nodePadding(10)
        .extent([[xPadding, 50], [width - xPadding, height - 50]])
        .nodeSort(null);  // CRITICAL: Don't let Sankey reorder nodes

    // Step 5: Apply layout (Sankey will handle Y positioning only)
    const graph = sankey({
        nodes: sankeyNodes,
        links: sankeyLinks
    });

    // Step 6: Force X positions by generation (override Sankey's auto-positioning)
    graph.nodes.forEach(node => {
        const gen = node.promptData.generation;
        const targetX = xPadding + (gen * generationSpacing);
        node.x0 = targetX;
        node.x1 = targetX + nodeWidth;

        console.log(`Node ${node.name.substring(0, 8)}... Gen ${gen} -> X: ${node.x0.toFixed(0)}`);
    });

    // Node heights are automatically sized by D3 Sankey based on flow volume
    // This means nodes with higher fitness delta flows will be taller

    console.log(`=== END LAYOUT ===\n`);

    // Create SVG
    const svg = d3.select('#sankey-container')
        .append('svg')
        .attr('width', width)
        .attr('height', height);

    // Create tooltip
    const tooltip = d3.select('body')
        .append('div')
        .attr('class', 'sankey-tooltip')
        .style('position', 'absolute')
        .style('visibility', 'hidden')
        .style('background', 'rgba(0, 0, 0, 0.9)')
        .style('color', '#fff')
        .style('padding', '12px')
        .style('border-radius', '4px')
        .style('font-size', '12px')
        .style('font-family', 'monospace')
        .style('max-width', '400px')
        .style('z-index', '10000')
        .style('pointer-events', 'none');

    // Draw links (flows)
    const link = svg.append('g')
        .selectAll('.link')
        .data(graph.links)
        .enter().append('path')
        .attr('class', 'link')
        .attr('d', d3.sankeyLinkHorizontal())
        .attr('stroke', d => getFitnessDeltaColor(d.fitnessDelta))
        .attr('stroke-width', d => Math.max(1, d.width))
        .attr('fill', 'none')
        .attr('opacity', 0.6)
        .style('cursor', 'pointer');

    // Link hover
    link.on('mouseover', function(event, d) {
        const arrow = d.fitnessDelta > 0 ? '↑' : d.fitnessDelta < 0 ? '↓' : '→';
        const color = getFitnessDeltaColor(d.fitnessDelta);

        // Extract UUIDs without -gen-N suffix for cleaner display
        const parentDisplayId = d.parent.prompt_id.split('-gen-')[0].substring(0, 12);
        const childDisplayId = d.child.prompt_id.split('-gen-')[0].substring(0, 12);

        // Get tag change summary
        const tagChanges = getTagChangeSummary(d.parent, d.child);

        const inheritedText = tagChanges.inherited.length > 0
            ? tagChanges.inherited.join(', ')
            : 'None';
        const changedText = tagChanges.changed.length > 0
            ? tagChanges.changed.join(', ')
            : 'None';

        tooltip.html(`
            <strong>Parent → Child Transition</strong><br>
            <hr style="border-color: #555; margin: 6px 0;">
            <strong>Parent:</strong> ${parentDisplayId}... (Gen ${d.parent.generation})<br>
            <strong>Child:</strong> ${childDisplayId}... (Gen ${d.child.generation})<br>
            <strong>Child Type:</strong> ${d.child.type}<br>
            <hr style="border-color: #555; margin: 6px 0;">
            <strong>Fitness Change:</strong> <span style="color: ${color}; font-size: 14px;">${arrow} ${d.fitnessDelta >= 0 ? '+' : ''}${d.fitnessDelta.toFixed(2)}</span><br>
            &nbsp;&nbsp;Parent: ${(d.parent.fitness || 0).toFixed(2)}<br>
            &nbsp;&nbsp;Child: ${(d.child.fitness || 0).toFixed(2)}<br>
            <hr style="border-color: #555; margin: 6px 0;">
            <strong>Tag Lineage:</strong><br>
            &nbsp;&nbsp;<span style="color: #10AC84;">Inherited unchanged:</span> ${inheritedText}<br>
            &nbsp;&nbsp;<span style="color: #EE5A6F;">Changed:</span> ${changedText}<br>
        `)
        .style('visibility', 'visible');

        d3.select(this).attr('opacity', 1.0);
    })
    .on('mousemove', function(event) {
        tooltip
            .style('top', (event.pageY - 10) + 'px')
            .style('left', (event.pageX + 10) + 'px');
    })
    .on('mouseout', function() {
        tooltip.style('visibility', 'hidden');
        d3.select(this).attr('opacity', 0.6);
    });

    // Draw nodes
    const node = svg.append('g')
        .selectAll('.node')
        .data(graph.nodes)
        .enter().append('g')
        .attr('class', 'node');

    // Node rectangles
    node.append('rect')
        .attr('x', d => d.x0)
        .attr('y', d => d.y0)
        .attr('height', d => d.y1 - d.y0)
        .attr('width', d => d.x1 - d.x0)
        .attr('fill', d => {
            // Color by type
            const typeColors = {
                'initial': '#10AC84',
                'mutation': '#EE5A6F',
                'crossover': '#F79F1F',
                'immigrant': '#9B59B6'
            };
            return typeColors[d.promptData.type] || '#95A5A6';
        })
        .attr('stroke', '#333')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer');

    // Node labels - Line 1: Prompt ID
    node.append('text')
        .attr('x', d => d.x0 < width / 2 ? d.x1 + 6 : d.x0 - 6)
        .attr('y', d => (d.y1 + d.y0) / 2 - 8)
        .attr('dy', '0.35em')
        .attr('text-anchor', d => d.x0 < width / 2 ? 'start' : 'end')
        .text(d => {
            const shortId = d.promptData.prompt_id.substring(0, 8);
            return `${shortId}...`;
        })
        .style('font-size', '10px')
        .style('font-family', 'monospace')
        .style('fill', '#2C3E50')
        .style('pointer-events', 'none');

    // Line 2: Generation
    node.append('text')
        .attr('x', d => d.x0 < width / 2 ? d.x1 + 6 : d.x0 - 6)
        .attr('y', d => (d.y1 + d.y0) / 2 + 4)
        .attr('dy', '0.35em')
        .attr('text-anchor', d => d.x0 < width / 2 ? 'start' : 'end')
        .text(d => `Gen ${d.promptData.generation}`)
        .style('font-size', '9px')
        .style('font-family', 'monospace')
        .style('fill', '#7F8C8D')
        .style('pointer-events', 'none');

    // Line 3: Fitness
    node.append('text')
        .attr('x', d => d.x0 < width / 2 ? d.x1 + 6 : d.x0 - 6)
        .attr('y', d => (d.y1 + d.y0) / 2 + 16)
        .attr('dy', '0.35em')
        .attr('text-anchor', d => d.x0 < width / 2 ? 'start' : 'end')
        .text(d => {
            const fitness = (d.promptData.fitness || 0).toFixed(2);
            return `F: ${fitness}`;
        })
        .style('font-size', '9px')
        .style('font-family', 'monospace')
        .style('fill', '#7F8C8D')
        .style('pointer-events', 'none');

    // Node hover
    node.on('mouseover', function(event, d) {
        const p = d.promptData;
        const parentIds = p.parents && p.parents.length > 0
            ? p.parents.map(id => id.substring(0, 20)).join(', ')
            : 'None (Gen 0)';

        // Extract just the UUID part without -gen-N for display
        const displayId = p.prompt_id.split('-gen-')[0].substring(0, 12);

        tooltip.html(`
            <strong>Prompt:</strong> ${displayId}...<br>
            <strong>Generation:</strong> ${p.generation} | <strong>Type:</strong> ${p.type}<br>
            <strong>Fitness:</strong> ${(p.fitness || 0).toFixed(2)}<br>
            <strong>Compression:</strong> ${(p.compression_ratio || 0).toFixed(2)}x | <strong>Quality:</strong> ${(p.quality_score_avg || 0).toFixed(2)}/10<br>
            <strong>Model:</strong> ${p.model_used || 'N/A'}<br>
            <strong>Parents:</strong> ${parentIds}<br>
            <hr style="border-color: #555; margin: 8px 0;">
            <strong>Tag Sources (how each tag arrived):</strong><br>
            &nbsp;&nbsp;Role: <span style="color: ${getSourceColor(p.role_source)}">${p.role_source}</span> (origin: ${p.role_origin})<br>
            &nbsp;&nbsp;Comp Target: <span style="color: ${getSourceColor(p.comp_source)}">${p.comp_source}</span> (origin: ${p.comp_origin})<br>
            &nbsp;&nbsp;Fidelity: <span style="color: ${getSourceColor(p.fidelity_source)}">${p.fidelity_source}</span> (origin: ${p.fidelity_origin})<br>
            &nbsp;&nbsp;Constraints: <span style="color: ${getSourceColor(p.constraints_source)}">${p.constraints_source}</span> (origin: ${p.constraints_origin})<br>
            &nbsp;&nbsp;Output: <span style="color: ${getSourceColor(p.output_source)}">${p.output_source}</span> (origin: ${p.output_origin})<br>
            <hr style="border-color: #555; margin: 8px 0;">
            <em>Click to explore this lineage</em>
        `)
        .style('visibility', 'visible');
    })
    .on('mousemove', function(event) {
        tooltip
            .style('top', (event.pageY - 10) + 'px')
            .style('left', (event.pageX + 10) + 'px');
    })
    .on('mouseout', function() {
        tooltip.style('visibility', 'hidden');
    });

    // Node click (drill down)
    node.on('click', function(event, d) {
        handleNodeClick(d.promptData.prompt_id);
    });
}
