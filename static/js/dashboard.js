/**
 * static/js/dashboard.js
 * Advance Billing — Dashboard Interactions
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobile Sidebar Toggle
    const mobileToggle = document.getElementById('mobile-menu-toggle');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    
    if (mobileToggle && sidebar) {
        mobileToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            sidebar.classList.toggle('open');
            if (sidebarOverlay) sidebarOverlay.classList.toggle('open');
        });
        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', () => {
                sidebar.classList.remove('open');
                sidebarOverlay.classList.remove('open');
            });
        }
        // Auto-close sidebar on mobile after clicking a link
        const navItems = sidebar.querySelectorAll('.nav-item');
        navItems.forEach(item => {
            item.addEventListener('click', () => {
                if (window.innerWidth <= 768) {
                    sidebar.classList.remove('open');
                    if (sidebarOverlay) sidebarOverlay.classList.remove('open');
                }
            });
        });
    }

    // 3. Initialize Chart.js (if canvas exists)
    const chartCanvas = document.getElementById('revenueChart');
    if (chartCanvas && typeof Chart !== 'undefined') {
        const ctx = chartCanvas.getContext('2d');
        
        function getThemeColors() {
            const computedStyle = getComputedStyle(document.documentElement);
            const accent = computedStyle.getPropertyValue('--color-accent').trim() || '#ff7a00';
            const accentSubtle = computedStyle.getPropertyValue('--color-accent-subtle').trim() || 'rgba(255, 122, 0, 0.12)';
            const grid = computedStyle.getPropertyValue('--color-border').trim() || 'rgba(255, 255, 255, 0.08)';
            const textSec = computedStyle.getPropertyValue('--color-text-secondary').trim() || '#9494b8';
            const textPri = computedStyle.getPropertyValue('--color-text-primary').trim() || '#f0f0f8';
            const bgCard = computedStyle.getPropertyValue('--color-bg-card').trim() || '#1a1a28';
            const bgSurface = computedStyle.getPropertyValue('--color-bg-surface').trim() || '#12121a';

            let areaBg = accentSubtle;
            if (accent.startsWith('#')) {
                areaBg = accent + '26'; // 15% opacity hex fallback
            }

            return { accent, areaBg, grid, textSec, textPri, bgCard, bgSurface };
        }

        const colors = getThemeColors();

        // Parse dynamic dataset from canvas attributes
        const labelsData = chartCanvas.dataset.labels ? JSON.parse(chartCanvas.dataset.labels) : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
        const valuesData = chartCanvas.dataset.values ? JSON.parse(chartCanvas.dataset.values) : [0, 0, 0, 0, 0, 0];
        const currencySymbol = chartCanvas.dataset.currency || '₹';

        // Set Chart.js global default font to Lora
        Chart.defaults.font.family = "'Lora'";

        const revenueChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labelsData,
                datasets: [{
                    label: 'Revenue',
                    data: valuesData,
                    borderColor: colors.accent,
                    backgroundColor: colors.areaBg,
                    borderWidth: 2.5,
                    tension: 0.35,
                    fill: true,
                    pointBackgroundColor: colors.accent,
                    pointBorderColor: colors.bgSurface,
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: colors.bgCard,
                        titleColor: colors.textPri,
                        titleFont: { family: "'Lora'", weight: '600' },
                        bodyColor: colors.textPri,
                        bodyFont: { family: "'Lora'", weight: '400' },
                        borderColor: colors.grid,
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            label: function(context) {
                                return ' Revenue: ' + currencySymbol + context.parsed.y.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: colors.textSec, font: { family: "'Lora'", size: 12 } }
                    },
                    y: {
                        beginAtZero: true,
                        suggestedMin: 0,
                        grid: { color: colors.grid },
                        ticks: {
                            color: colors.textSec,
                            font: { family: "'Lora'", size: 12 },
                            callback: (value) => currencySymbol + (value >= 1000 ? (value/1000) + 'k' : value)
                        }
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        });

        // Watch for data-theme attribute updates (live preview / settings change)
        const themeObserver = new MutationObserver(() => {
            const updatedColors = getThemeColors();
            revenueChart.data.datasets[0].borderColor = updatedColors.accent;
            revenueChart.data.datasets[0].backgroundColor = updatedColors.areaBg;
            revenueChart.data.datasets[0].pointBackgroundColor = updatedColors.accent;
            revenueChart.data.datasets[0].pointBorderColor = updatedColors.bgSurface;
            revenueChart.options.plugins.tooltip.backgroundColor = updatedColors.bgCard;
            revenueChart.options.plugins.tooltip.borderColor = updatedColors.grid;
            revenueChart.options.plugins.tooltip.titleColor = updatedColors.textPri;
            revenueChart.options.plugins.tooltip.bodyColor = updatedColors.textPri;
            revenueChart.options.scales.x.ticks.color = updatedColors.textSec;
            revenueChart.options.scales.y.ticks.color = updatedColors.textSec;
            revenueChart.options.scales.y.grid.color = updatedColors.grid;
            revenueChart.update();
        });
        themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }
});
