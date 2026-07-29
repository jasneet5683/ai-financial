/**
 * script.js
 * Handles frontend logic for AI Financial Advisor
 * - Tab switching
 * - API calls to backend
 * - Result formatting and display
 */

const BASE_URL = window.location.origin; // Works for both local dev and Railway deployment

// ---------- Tab Switching ----------
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.getAttribute('data-tab');
        
        // Deactivate all tabs and buttons
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        
        // Activate selected tab and button
        document.getElementById(tabName).classList.add('active');
        btn.classList.add('active');
    });
});

// ---------- Stock Analysis ----------
document.getElementById('analyze-stock-btn').addEventListener('click', async () => {
    const symbol = document.getElementById('stock-symbol').value.trim();
    const exchange = document.getElementById('stock-exchange').value;
    const question = document.getElementById('stock-question').value.trim();

    if (!symbol) {
        showError('stock', 'Please enter a stock symbol');
        return;
    }

    showLoading('stock');
    try {
        const response = await fetch(`${BASE_URL}/api/analyze-stock`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, exchange, question: question || undefined })
        });

        const data = await response.json();

        if (!response.ok) {
            showError('stock', data.error || 'Failed to analyze stock');
            return;
        }

        renderStockAnalysis(data);
    } catch (error) {
        showError('stock', `Error: ${error.message}`);
    }
});

// ---------- Portfolio Analysis ----------
document.getElementById('analyze-portfolio-btn').addEventListener('click', async () => {
    const question = document.getElementById('portfolio-question').value.trim();

    showLoading('portfolio');
    try {
        const response = await fetch(`${BASE_URL}/api/analyze-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: question || undefined })
        });

        const data = await response.json();

        if (!response.ok) {
            showError('portfolio', data.error || 'Failed to analyze portfolio');
            return;
        }

        renderPortfolioAnalysis(data);
    } catch (error) {
        showError('portfolio', `Error: ${error.message}`);
    }
});

// ---------- Render Stock Analysis ----------
function renderStockAnalysis(data) {
    const { stock_data, analysis } = data;

    let html = '<div class="analysis-card">';
    html += `<h3>${stock_data.company_name || stock_data.ticker}</h3>`;

    // Stock metrics table
    html += '<table class="stock-data-table"><tr><th>Metric</th><th>Value</th></tr>';
    html += `<tr><td>Current Price</td><td>${formatValue(stock_data.current_price)} ${stock_data.currency}</td></tr>`;
    html += `<tr><td>Day Change</td><td>${formatValue(stock_data.day_change_pct)}%</td></tr>`;
    html += `<tr><td>P/E Ratio</td><td>${formatValue(stock_data.pe_ratio)}</td></tr>`;
    html += `<tr><td>EPS</td><td>${formatValue(stock_data.eps)}</td></tr>`;
    html += `<tr><td>Market Cap</td><td>${formatValue(stock_data.market_cap)}</td></tr>`;
    html += `<tr><td>52W High/Low</td><td>${formatValue(stock_data['52_week_high'])} / ${formatValue(stock_data['52_week_low'])}</td></tr>`;
    html += '</table>';

    // AI Analysis
    if (analysis.error) {
        html += `<div class="error">${analysis.error}</div>`;
    } else {
        html += `<div class="analysis-card"><strong>Executive Summary:</strong><p>${analysis.executive_summary}</p></div>`;
        html += `<div class="analysis-card"><strong>Key Metrics Commentary:</strong><p>${analysis.key_metrics_commentary}</p></div>`;

        if (analysis.risks && analysis.risks.length) {
            html += '<div class="analysis-card"><strong>Risks:</strong><ul>';
            analysis.risks.forEach(r => {
                const severity = r.severity ? ` <span class="risk-${r.severity.toLowerCase()}">[${r.severity}]</span>` : '';
                html += `<li>${r.risk}${severity}: ${r.detail}</li>`;
            });
            html += '</ul></div>';
        }

        if (analysis.opportunities && analysis.opportunities.length) {
            html += '<div class="analysis-card"><strong>Opportunities:</strong><ul>';
            analysis.opportunities.forEach(o => {
                html += `<li>${o.opportunity}: ${o.detail}</li>`;
            });
            html += '</ul></div>';
        }

        if (analysis.scenario_analysis) {
            html += '<div class="analysis-card"><strong>Scenario Analysis:</strong>';
            html += `<p><strong>Bull Case:</strong> ${analysis.scenario_analysis.bull_case}</p>`;
            html += `<p><strong>Base Case:</strong> ${analysis.scenario_analysis.base_case}</p>`;
            html += `<p><strong>Bear Case:</strong> ${analysis.scenario_analysis.bear_case}</p>`;
            html += '</div>';
        }

        html += `<div class="recommendation">${analysis.recommendation}</div>`;
        html += `<div class="analysis-card"><strong>Rationale:</strong><p>${analysis.rationale}</p><p><strong>Confidence:</strong> ${analysis.confidence_level}</p></div>`;
    }

    html += '</div>';
    showResult('stock', html);
}

// ---------- Render Portfolio Analysis ----------
function renderPortfolioAnalysis(data) {
    const { portfolio_data, analysis } = data;

    let html = '<div class="analysis-card">';
    html += '<h2>Portfolio Analysis</h2>';

    // Portfolio holdings table
    html += '<table class="stock-data-table"><tr><th>Ticker</th><th>Qty</th><th>Buy Price</th><th>Current Value</th><th>P&L</th><th>P&L %</th></tr>';
    portfolio_data.forEach(h => {
        const pnl = h.pnl !== 'Not available' ? formatValue(h.pnl) : 'N/A';
        const pnlPct = h.pnl_pct !== null ? `${formatValue(h.pnl_pct)}%` : 'N/A';
        html += `<tr><td>${h.ticker}</td><td>${h.quantity}</td><td>${formatValue(h.buy_price)}</td><td>${formatValue(h.current_value)}</td><td>${pnl}</td><td>${pnlPct}</td></tr>`;
    });
    html += '</table>';

    // AI Analysis
    if (analysis.error) {
        html += `<div class="error">${analysis.error}</div>`;
    } else {
        html += `<div class="analysis-card"><strong>Executive Summary:</strong><p>${analysis.executive_summary}</p></div>`;
        html += `<div class="analysis-card"><strong>Diversification Assessment:</strong><p>${analysis.diversification_assessment}</p></div>`;

        if (analysis.risks && analysis.risks.length) {
            html += '<div class="analysis-card"><strong>Portfolio Risks:</strong><ul>';
            analysis.risks.forEach(r => {
                const severity = r.severity ? ` <span class="risk-${r.severity.toLowerCase()}">[${r.severity}]</span>` : '';
                html += `<li>${r.risk}${severity}: ${r.detail}</li>`;
            });
            html += '</ul></div>';
        }

        if (analysis.top_performers && analysis.top_performers.length) {
            html += '<div class="analysis-card"><strong>Top Performers:</strong><ul>';
            analysis.top_performers.forEach(p => {
                html += `<li><strong>${p.ticker}:</strong> ${p.reason}</li>`;
            });
            html += '</ul></div>';
        }

        if (analysis.underperformers && analysis.underperformers.length) {
            html += '<div class="analysis-card"><strong>Underperformers:</strong><ul>';
            analysis.underperformers.forEach(u => {
                html += `<li><strong>${u.ticker}:</strong> ${u.reason} → ${u.action_suggested}</li>`;
            });
            html += '</ul></div>';
        }

        if (analysis.rebalancing_suggestions && analysis.rebalancing_suggestions.length) {
            html += '<div class="analysis-card"><strong>Rebalancing Suggestions:</strong><ul>';
            analysis.rebalancing_suggestions.forEach(s => {
                html += `<li>${s.suggestion}: ${s.rationale}</li>`;
            });
            html += '</ul></div>';
        }

        html += `<div class="recommendation">${analysis.overall_recommendation}</div>`;
        html += `<p><strong>Confidence:</strong> ${analysis.confidence_level}</p>`;
    }

    html += '</div>';
    showResult('portfolio', html);
}

// ---------- Helper Functions ----------
function showLoading(type) {
    document.getElementById(`${type}-loading`).classList.remove('hidden');
    document.getElementById(`${type}-error`).classList.add('hidden');
    document.getElementById(`${type}-result`).classList.add('hidden');
}

function showError(type, message) {
    document.getElementById(`${type}-loading`).classList.add('hidden');
    document.getElementById(`${type}-error`).textContent = message;
    document.getElementById(`${type}-error`).classList.remove('hidden');
    document.getElementById(`${type}-result`).classList.add('hidden');
}

function showResult(type, html) {
    document.getElementById(`${type}-loading`).classList.add('hidden');
    document.getElementById(`${type}-error`).classList.add('hidden');
    document.getElementById(`${type}-result`).innerHTML = html;
    document.getElementById(`${type}-result`).classList.remove('hidden');
}

function formatValue(value) {
    if (value === null || value === undefined || value === 'Not available') {
        return '—';
    }
    if (typeof value === 'number') {
        return value.toLocaleString('en-IN', { maximumFractionDigits: 2 });
    }
    return value;
}
