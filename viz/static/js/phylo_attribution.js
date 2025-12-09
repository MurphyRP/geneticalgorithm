/**
 * Phylogenetic Attribution Analysis - Frontend Logic
 *
 * Visualizes tag impact on fitness through evolutionary lineage tracing.
 * Requires single-tag mutation eras for clean attribution.
 */

let currentEra = null;
let currentData = {
    tagMetrics: null,
    tagDeltas: null
};

// ============================================================================
// Page Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    loadEras();

    // Set up era selector change handler
    document.getElementById('era-select').addEventListener('change', function(e) {
        const era = e.target.value;
        if (era) {
            loadEraData(era);
        }
    });
});

// ============================================================================
// Data Loading
// ============================================================================

async function loadEras() {
    try {
        const response = await fetch('/api/phylo_attribution/eras');
        const eras = await response.json();

        if (eras.error) {
            showError('Failed to load eras: ' + eras.error);
            return;
        }

        const select = document.getElementById('era-select');

        if (eras.length === 0) {
            select.innerHTML = '<option value="">No single-tag eras available</option>';
            showError('No eras with single_tag=true found. Phylogenetic attribution requires single-tag mutation eras.');
            return;
        }

        // Populate dropdown
        select.innerHTML = eras.map(e =>
            `<option value="${e.era}">${e.era} (${e.max_generation + 1} gens, ${e.total_prompts} prompts)</option>`
        ).join('');

        // Auto-load first era
        if (eras.length > 0) {
            currentEra = eras[0].era;
            select.value = currentEra;
            loadEraData(currentEra);
        }

    } catch (error) {
        showError('Failed to load eras: ' + error.message);
    }
}

async function loadEraData(era) {
    console.log('loadEraData called with era:', era);
    currentEra = era;

    // Show loading state
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('error-message').classList.add('hidden');
    document.getElementById('delta-section').classList.add('hidden');

    try {
        console.log('Fetching data for era:', era);
        // Load both datasets in parallel
        const [metricsResponse, deltasResponse] = await Promise.all([
            fetch(`/api/phylo_attribution/tag_metrics/${era}`),
            fetch(`/api/phylo_attribution/tag_type_deltas/${era}`)
        ]);

        console.log('Responses received');
        const metrics = await metricsResponse.json();
        const deltas = await deltasResponse.json();

        console.log('Data parsed:', {metrics, deltas});

        if (metrics.error) {
            throw new Error('Metrics: ' + metrics.error);
        }
        if (deltas.error) {
            throw new Error('Deltas: ' + deltas.error);
        }

        currentData.tagMetrics = metrics;
        currentData.tagDeltas = deltas;

        // Hide loading, show content
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('delta-section').classList.remove('hidden');

        console.log('Rendering delta analysis');
        // Render visualizations
        renderDeltaAnalysis(deltas);
        console.log('Render complete');
        // Static metrics removed - success rate breakdown is more useful

    } catch (error) {
        console.error('Error loading era data:', error);
        document.getElementById('loading').classList.add('hidden');
        showError('Failed to load era data: ' + error.message);
    }
}

// ============================================================================
// Delta Analysis Visualization
// ============================================================================

function renderDeltaAnalysis(data) {
    const deltas = data.tag_type_deltas;

    if (!deltas || deltas.length === 0) {
        document.getElementById('delta-chart').innerHTML = '<p style="color: #7F8C8D; text-align: center; padding: 40px;">No mutation data available</p>';
        return;
    }

    // Sort by positive rate descending (highest success rate first)
    deltas.sort((a, b) => b.positive_rate - a.positive_rate);

    // Prepare data for grouped horizontal bar chart
    const tagTypes = deltas.map(d => d.tag_type.replace('_', ' '));
    const positiveRates = deltas.map(d => d.positive_rate * 100); // As percentage for bar length
    const negativeRates = deltas.map(d => (1 - d.positive_rate) * 100); // As percentage for bar length

    const meanPositiveDeltas = deltas.map(d => d.mean_positive_delta || 0);
    const meanNegativeDeltas = deltas.map(d => d.mean_negative_delta || 0);
    const changeCounts = deltas.map(d => d.change_count);
    const positiveCounts = deltas.map(d => d.positive_count);
    const negativeCounts = deltas.map(d => d.negative_count);

    // Positive improvements trace (purple) - BAR LENGTH = SUCCESS RATE %
    const positiveTrace = {
        type: 'bar',
        x: positiveRates,
        y: tagTypes,
        orientation: 'h',
        name: 'Success Rate',
        marker: {
            color: '#667EEA'
        },
        text: positiveRates.map((rate, i) => `${rate.toFixed(1)}%`),
        textposition: 'auto',
        customdata: deltas.map((d, i) => ({
            rate: positiveRates[i].toFixed(1),
            count: positiveCounts[i],
            totalChanges: changeCounts[i],
            meanDelta: meanPositiveDeltas[i]
        })),
        hovertemplate: '<b>%{y} - Success Rate</b><br>' +
                       'Success Rate: %{customdata.rate}% (%{customdata.count} of %{customdata.totalChanges})<br>' +
                       'Mean Improvement: +%{customdata.meanDelta:.4f} fitness<br>' +
                       '<extra></extra>'
    };

    // Negative impacts trace (red) - BAR LENGTH = FAILURE RATE %
    const negativeTrace = {
        type: 'bar',
        x: negativeRates,
        y: tagTypes,
        orientation: 'h',
        name: 'Failure Rate',
        marker: {
            color: '#E74C3C'
        },
        text: negativeRates.map((rate, i) => `${rate.toFixed(1)}%`),
        textposition: 'auto',
        customdata: deltas.map((d, i) => ({
            rate: negativeRates[i].toFixed(1),
            count: negativeCounts[i],
            totalChanges: changeCounts[i],
            meanDelta: meanNegativeDeltas[i]
        })),
        hovertemplate: '<b>%{y} - Failure Rate</b><br>' +
                       'Failure Rate: %{customdata.rate}% (%{customdata.count} of %{customdata.totalChanges})<br>' +
                       'Mean Harm: %{customdata.meanDelta:.4f} fitness<br>' +
                       '<extra></extra>'
    };

    const layout = {
        title: {
            text: 'Tag Type Success/Failure Rates (when tag changes)',
            font: { color: '#2C3E50', size: 20, weight: 600 }
        },
        xaxis: {
            title: 'Percentage of Changes (%)',
            zeroline: false,
            gridcolor: '#E8ECEF',
            color: '#2C3E50',
            range: [0, 100],
            titlefont: { size: 16, color: '#2C3E50' },
            tickfont: { size: 14 }
        },
        yaxis: {
            gridcolor: '#E8ECEF',
            color: '#2C3E50',
            tickfont: { size: 14 }
        },
        barmode: 'group',
        plot_bgcolor: 'white',
        paper_bgcolor: 'white',
        font: { color: '#2C3E50', family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif' },
        margin: { l: 150, r: 50, t: 80, b: 80 },
        height: 500,
        legend: {
            orientation: 'h',
            y: -0.15,
            x: 0.5,
            xanchor: 'center',
            font: { size: 14, color: '#2C3E50' }
        }
    };

    Plotly.newPlot('delta-chart', [positiveTrace, negativeTrace], layout, {responsive: true});
}

// ============================================================================
// Static Metrics Visualization
// ============================================================================

function renderStaticMetrics(data) {
    const container = document.getElementById('metrics-content');
    container.innerHTML = '';

    const tagTypes = ['role', 'compression_target', 'fidelity', 'constraints', 'output'];

    tagTypes.forEach(tagType => {
        const tagData = data.tag_types[tagType];

        if (!tagData || !tagData.variants || tagData.variants.length === 0) {
            return; // Skip if no data
        }

        // Create section for this tag type
        const section = document.createElement('div');
        section.className = 'tag-type-section';
        section.id = `metrics-${tagType}`;

        const header = document.createElement('div');
        header.className = 'tag-type-header';
        header.innerHTML = `<div class="tag-type-title">${tagType.replace('_', ' ')}</div>`;

        const chartGrid = document.createElement('div');
        chartGrid.className = 'chart-grid';

        // Create 3 chart containers
        const fitnessDiv = document.createElement('div');
        fitnessDiv.className = 'chart-container';
        fitnessDiv.innerHTML = '<div class="chart-title">Mean Fitness</div>';
        const fitnessChart = document.createElement('div');
        fitnessChart.id = `chart-${tagType}-fitness`;
        fitnessDiv.appendChild(fitnessChart);

        const qualityDiv = document.createElement('div');
        qualityDiv.className = 'chart-container';
        qualityDiv.innerHTML = '<div class="chart-title">Mean Quality Score</div>';
        const qualityChart = document.createElement('div');
        qualityChart.id = `chart-${tagType}-quality`;
        qualityDiv.appendChild(qualityChart);

        const compressionDiv = document.createElement('div');
        compressionDiv.className = 'chart-container';
        compressionDiv.innerHTML = '<div class="chart-title">Mean Compression Ratio</div>';
        const compressionChart = document.createElement('div');
        compressionChart.id = `chart-${tagType}-compression`;
        compressionDiv.appendChild(compressionChart);

        chartGrid.appendChild(fitnessDiv);
        chartGrid.appendChild(qualityDiv);
        chartGrid.appendChild(compressionDiv);

        section.appendChild(header);
        section.appendChild(chartGrid);
        container.appendChild(section);

        // Render the three charts
        renderMetricChart(tagType, 'fitness', tagData.variants);
        renderMetricChart(tagType, 'quality', tagData.variants);
        renderMetricChart(tagType, 'compression', tagData.variants);
    });
}

function renderMetricChart(tagType, metric, variants) {
    // Sort by metric descending and take top 10
    let sortedVariants = [...variants];

    const metricField = metric === 'fitness' ? 'mean_fitness' :
                       metric === 'quality' ? 'mean_quality' :
                       'mean_compression_ratio';

    sortedVariants.sort((a, b) => b[metricField] - a[metricField]);
    sortedVariants = sortedVariants.slice(0, 10);

    // Prepare data
    const labels = sortedVariants.map(v => v.text_snippet || 'N/A');
    const values = sortedVariants.map(v => v[metricField]);
    const counts = sortedVariants.map(v => v.prompt_count);
    const guids = sortedVariants.map(v => v.guid);
    const fullTexts = sortedVariants.map(v => v.text_full || v.text_snippet);

    const trace = {
        type: 'bar',
        x: labels,
        y: values,
        marker: {
            color: '#667EEA',
            opacity: 0.8
        },
        text: counts,
        customdata: guids.map((guid, i) => ({
            guid: guid,
            tagType: tagType,
            fullText: fullTexts[i]
        })),
        hovertemplate: '<b>%{x}</b><br>' +
                       `${metric === 'fitness' ? 'Fitness' : metric === 'quality' ? 'Quality' : 'Compression'}: %{y:.3f}<br>` +
                       'Prompts: %{text}<br>' +
                       '<extra></extra>'
    };

    const layout = {
        xaxis: {
            tickangle: -45,
            gridcolor: '#E8ECEF',
            color: '#2C3E50',
            showticklabels: false  // Hide x-axis labels to save space
        },
        yaxis: {
            gridcolor: '#E8ECEF',
            color: '#2C3E50',
            title: metric === 'fitness' ? 'Fitness' :
                   metric === 'quality' ? 'Quality (0-10)' :
                   'Ratio'
        },
        plot_bgcolor: 'white',
        paper_bgcolor: '#F8F9FA',
        font: { color: '#2C3E50', size: 10 },
        margin: { l: 50, r: 10, t: 10, b: 40 },
        height: 250
    };

    const config = { responsive: true };

    Plotly.newPlot(`chart-${tagType}-${metric}`, [trace], layout, config);

    // Add click handler for lineage tracing
    document.getElementById(`chart-${tagType}-${metric}`).on('plotly_click', function(data) {
        const point = data.points[0];
        const customdata = point.customdata;
        showLineageModal(customdata.guid, customdata.tagType, customdata.fullText);
    });
}

// ============================================================================
// Lineage Modal
// ============================================================================

async function showLineageModal(tagGuid, tagType, tagText) {
    const modal = document.getElementById('lineage-modal');
    const content = document.getElementById('lineage-content');

    // Show modal with loading state
    modal.classList.add('active');
    content.innerHTML = '<p style="color: #7F8C8D; text-align: center; padding: 40px;">Loading lineage...</p>';

    try {
        const response = await fetch(`/api/phylo_attribution/tag_lineage/${currentEra}/${tagGuid}?tag_type=${tagType}`);
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Render lineage
        let html = '';

        // Current tag
        html += '<div class="lineage-item">';
        html += '<h4>Current Tag</h4>';
        html += `<p><strong>Type:</strong> ${tagType.replace('_', ' ')}</p>`;
        html += `<p><strong>Text:</strong> ${tagText}</p>`;
        html += `<p><strong>Origin:</strong> ${data.lineage.current.origin}</p>`;
        html += `<p><strong>Generations:</strong> ${data.lineage.current.first_generation} - ${data.lineage.current.last_generation}</p>`;
        html += `<p><strong>Prompts:</strong> ${data.lineage.current.prompt_count}</p>`;
        html += `<p><strong>Mean Fitness:</strong> ${data.lineage.current.mean_fitness.toFixed(4)}</p>`;
        html += '</div>';

        // Ancestors
        if (data.lineage.ancestors && data.lineage.ancestors.length > 0) {
            html += '<h3 style="color: #667EEA; margin: 20px 0 10px; font-size: 1.2em;">Ancestors</h3>';
            data.lineage.ancestors.forEach(ancestor => {
                html += '<div class="lineage-item">';
                html += `<h4>Depth ${ancestor.depth} (Parent${ancestor.depth > 1 ? "'s".repeat(ancestor.depth - 1) + " parent" : ''})</h4>`;
                html += `<p><strong>Text:</strong> ${ancestor.text.substring(0, 100)}...</p>`;
                html += `<p><strong>Origin:</strong> ${ancestor.origin}</p>`;
                html += `<p><strong>Generations:</strong> ${ancestor.first_generation} - ${ancestor.last_generation}</p>`;
                html += `<p><strong>Mean Fitness:</strong> ${ancestor.mean_fitness.toFixed(4)}</p>`;
                html += '</div>';
            });
        } else {
            html += '<h3 style="color: #7F8C8D; margin: 20px 0 10px; font-size: 1.2em;">No Ancestors (initial or immigrant)</h3>';
        }

        // Children
        if (data.lineage.children && data.lineage.children.length > 0) {
            html += '<h3 style="color: #667EEA; margin: 20px 0 10px; font-size: 1.2em;">Children (Mutations spawned from this tag)</h3>';
            data.lineage.children.forEach(child => {
                html += '<div class="lineage-item">';
                html += `<p><strong>Text:</strong> ${child.text.substring(0, 100)}...</p>`;
                html += `<p><strong>Origin:</strong> ${child.origin}</p>`;
                html += `<p><strong>Generations:</strong> ${child.first_generation} - ${child.last_generation}</p>`;
                html += `<p><strong>Mean Fitness:</strong> ${child.mean_fitness.toFixed(4)}</p>`;
                html += '</div>';
            });
        } else {
            html += '<h3 style="color: #7F8C8D; margin: 20px 0 10px; font-size: 1.2em;">No Children</h3>';
        }

        content.innerHTML = html;

    } catch (error) {
        content.innerHTML = `<p class="error">Failed to load lineage: ${error.message}</p>`;
    }
}

function closeLineageModal() {
    document.getElementById('lineage-modal').classList.remove('active');
}

// Close modal on background click
document.getElementById('lineage-modal').addEventListener('click', function(e) {
    if (e.target.id === 'lineage-modal') {
        closeLineageModal();
    }
});

// ============================================================================
// Utility Functions
// ============================================================================

function showError(message) {
    const errorDiv = document.getElementById('error-message');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
    document.getElementById('loading').classList.add('hidden');
}
