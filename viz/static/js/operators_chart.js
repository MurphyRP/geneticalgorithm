/**
 * Operator Effectiveness Box Plot Chart
 *
 * Compares fitness distributions across operator types (mutation, crossover, immigrant).
 * Uses box plots to show median, quartiles, and outliers for each operator.
 *
 * Why this works for weak signal:
 * - Shows RELATIVE performance even if absolute gains are small
 * - Reveals which operators to keep/drop for future experiments
 * - Highlights variance within each operator type
 *
 * Used by: dashboard.html
 * Requires: prompts data with fitness and type fields
 */

function renderOperatorsChart(prompts) {
    // Filter out generation 0 (only interested in evolved prompts)
    const evolvedPrompts = prompts.filter(p => p.generation > 0);

    if (evolvedPrompts.length === 0) {
        document.getElementById('operators-chart').innerHTML =
            '<p class="no-data">No evolved prompts yet. Run evolution first.</p>';
        return;
    }

    // Group by operator type
    const operators = ['mutation', 'crossover', 'immigrant'];
    const colors = {
        'mutation': '#EE5A6F',
        'crossover': '#F79F1F',
        'immigrant': '#9B59B6'
    };

    const traces = operators.map(op => {
        const opPrompts = evolvedPrompts.filter(p => p.type === op);

        return {
            y: opPrompts.map(p => p.fitness),
            name: op.charAt(0).toUpperCase() + op.slice(1),
            type: 'box',
            marker: {
                color: colors[op]
            },
            boxmean: 'sd',  // Show mean and std dev
            boxpoints: 'outliers'  // Show outlier points
        };
    });

    const layout = {
        title: {
            text: 'Fitness Distribution by Operator Type',
            font: { size: 18 }
        },
        yaxis: {
            title: 'Fitness Score',
            showgrid: true
        },
        xaxis: {
            title: 'Operator Type'
        },
        showlegend: false,
        margin: {
            l: 60,
            r: 40,
            t: 60,
            b: 60
        }
    };

    const config = {
        responsive: true,
        displayModeBar: true,
        displaylogo: false
    };

    Plotly.newPlot('operators-chart', traces, layout, config);
}
