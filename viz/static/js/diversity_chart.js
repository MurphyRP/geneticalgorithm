/**
 * Tag Diversity Timeline Chart
 *
 * Tracks unique tag counts per generation for all 5 tag types.
 * Shows convergence (lines decline) vs sustained diversity (lines stable).
 *
 * Why this works for weak signal:
 * - High diversity + weak fitness → tags don't correlate with fitness
 * - Low diversity + weak fitness → premature convergence (bad)
 * - Low diversity + strong fitness → convergence to optimal (good)
 *
 * Used by: dashboard.html
 * Requires: diversity data from /api/diversity/<era>
 */

function renderDiversityChart(diversity) {
    const tagTypes = [
        { key: 'role_unique', name: 'Role', color: '#3498DB' },
        { key: 'comp_unique', name: 'Compression Target', color: '#E74C3C' },
        { key: 'fidelity_unique', name: 'Fidelity', color: '#2ECC71' },
        { key: 'constraints_unique', name: 'Constraints', color: '#F39C12' },
        { key: 'output_unique', name: 'Output', color: '#9B59B6' }
    ];

    const traces = tagTypes.map(tag => ({
        x: diversity.map(d => d.generation),
        y: diversity.map(d => d[tag.key]),
        mode: 'lines+markers',
        name: tag.name,
        line: {
            color: tag.color,
            width: 2
        },
        marker: {
            size: 6
        }
    }));

    const layout = {
        title: {
            text: 'Tag Diversity Across Generations',
            font: { size: 18 }
        },
        xaxis: {
            title: 'Generation',
            showgrid: true,
            dtick: 1  // Only show integer generation numbers
        },
        yaxis: {
            title: 'Unique Tag Count',
            showgrid: true,
            rangemode: 'tozero'
        },
        hovermode: 'x unified',
        showlegend: true,
        legend: {
            x: 1.02,
            y: 1,
            xanchor: 'left'
        },
        margin: {
            l: 60,
            r: 140,
            t: 60,
            b: 60
        }
    };

    const config = {
        responsive: true,
        displayModeBar: true,
        displaylogo: false
    };

    Plotly.newPlot('diversity-chart', traces, layout, config);
}
