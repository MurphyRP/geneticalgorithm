/**
 * Fitness Trajectory Chart
 *
 * Visualizes fitness evolution across generations with:
 * - Mean fitness line (bold, primary trend)
 * - ±1 std dev shaded band (shows variance)
 * - Individual prompts as scatter points (colored by operator type)
 *
 * Why this works for weak signal:
 * - Flat line shows plateau (still interesting)
 * - Wide band shows high variance (evaluation issue?)
 * - Declining line shows harmful evolution (also valuable data)
 *
 * Used by: dashboard.html (called on era selection)
 * Requires: generations data (with mean/std), prompts data (with fitness/type)
 */

function renderFitnessChart(generations, prompts) {
    // Prepare mean fitness line data
    const meanTrace = {
        x: generations.map(g => g.generation),
        y: generations.map(g => g.mean_fitness),
        mode: 'lines',
        name: 'Mean Fitness',
        line: {
            color: '#2E86DE',
            width: 3
        }
    };

    // Prepare std dev band (upper bound)
    const upperTrace = {
        x: generations.map(g => g.generation),
        y: generations.map(g => g.mean_fitness + g.std_fitness),
        mode: 'lines',
        name: '+1 Std Dev',
        line: {
            color: 'rgba(46, 134, 222, 0)',
            width: 0
        },
        fillcolor: 'rgba(46, 134, 222, 0.2)',
        fill: 'tonexty',
        showlegend: false
    };

    // Prepare std dev band (lower bound)
    const lowerTrace = {
        x: generations.map(g => g.generation),
        y: generations.map(g => Math.max(0, g.mean_fitness - g.std_fitness)),
        mode: 'lines',
        name: '-1 Std Dev',
        line: {
            color: 'rgba(46, 134, 222, 0)',
            width: 0
        },
        showlegend: false
    };

    // Prepare individual prompt scatter points by type
    const typeColors = {
        'initial': '#10AC84',      // Green
        'mutation': '#EE5A6F',     // Red
        'crossover': '#F79F1F',    // Orange
        'immigrant': '#9B59B6'     // Purple
    };

    // Group prompts by type (only exclude prompts without fitness scores)
    const promptsByType = {};
    prompts.forEach(p => {
        // Only include prompts that have been evaluated (have fitness scores)
        if (p.fitness != null && p.fitness > 0) {
            if (!promptsByType[p.type]) {
                promptsByType[p.type] = [];
            }
            promptsByType[p.type].push(p);
        }
    });

    // Create scatter trace for each type
    const scatterTraces = Object.entries(promptsByType).map(([type, typePrompts]) => ({
        x: typePrompts.map(p => p.generation),
        y: typePrompts.map(p => p.fitness),
        mode: 'markers',
        name: type.charAt(0).toUpperCase() + type.slice(1),
        marker: {
            color: typeColors[type] || '#95A5A6',
            size: 6,
            opacity: 0.6
        },
        type: 'scatter'
    }));

    // Combine all traces
    const data = [lowerTrace, upperTrace, meanTrace, ...scatterTraces];

    // Layout configuration
    const layout = {
        title: {
            text: 'Fitness Evolution Across Generations',
            font: { size: 18 }
        },
        xaxis: {
            title: 'Generation',
            showgrid: true,
            zeroline: false,
            dtick: 1,  // Only show integer generation numbers (0, 1, 2, 3...)
            range: [-0.5, generations[generations.length - 1].generation + 0.5]  // Exact data range with minimal padding
        },
        yaxis: {
            title: 'Fitness Score',
            showgrid: true,
            zeroline: false
        },
        hovermode: 'closest',
        showlegend: true,
        legend: {
            x: 1.02,
            y: 1,
            xanchor: 'left'
        },
        margin: {
            l: 60,
            r: 120,
            t: 60,
            b: 60
        }
    };

    // Plotly config (toolbar options)
    const config = {
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d']
    };

    // Render chart
    Plotly.newPlot('fitness-chart', data, layout, config);
}
