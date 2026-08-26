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

    // 2. User Dropdown Menu
    const userMenuBtn = document.getElementById('user-menu-btn');
    const userMenuDropdown = document.getElementById('user-menu-dropdown');
    
    if (userMenuBtn && userMenuDropdown) {
        userMenuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            userMenuDropdown.classList.toggle('show');
        });
        
        // Close when clicking outside
        document.addEventListener('click', (e) => {
            if (!userMenuBtn.contains(e.target) && !userMenuDropdown.contains(e.target)) {
                userMenuDropdown.classList.remove('show');
            }
        });
    }

    // 3. Initialize Chart.js (if canvas exists)
    const chartCanvas = document.getElementById('revenueChart');
    if (chartCanvas && typeof Chart !== 'undefined') {
        const ctx = chartCanvas.getContext('2d');
        
        // Get primary accent color from CSS variables
        const computedStyle = getComputedStyle(document.documentElement);
        const accentColor = computedStyle.getPropertyValue('--palette-accent-400').trim() || '#ff9933';
        const gridColor = computedStyle.getPropertyValue('--color-border').trim() || 'rgba(255, 255, 255, 0.1)';
        const textColor = computedStyle.getPropertyValue('--color-text-secondary').trim() || '#9494b8';

        // Parse dynamic dataset from canvas attributes
        const labelsData = chartCanvas.dataset.labels ? JSON.parse(chartCanvas.dataset.labels) : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
        const valuesData = chartCanvas.dataset.values ? JSON.parse(chartCanvas.dataset.values) : [0, 0, 0, 0, 0, 0];
        const currencySymbol = chartCanvas.dataset.currency || '₹';

        // Set Chart.js global default font to Lora
        Chart.defaults.font.family = "'Lora'";

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: labelsData,
                datasets: [{
                    label: 'Revenue',
                    data: valuesData,
                    borderColor: accentColor,
                    backgroundColor: `${accentColor}26`, // 15% opacity
                    borderWidth: 2.5,
                    tension: 0.35,
                    fill: true,
                    pointBackgroundColor: accentColor,
                    pointBorderColor: '#12121a',
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
                        backgroundColor: '#1a1a28',
                        titleColor: '#fff',
                        titleFont: { family: "'Lora'", weight: '600' },
                        bodyColor: '#fff',
                        bodyFont: { family: "'Lora'", weight: '400' },
                        borderColor: 'rgba(255,255,255,0.1)',
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
                        ticks: { color: textColor, font: { family: "'Lora'", size: 12 } }
                    },
                    y: {
                        beginAtZero: true,
                        suggestedMin: 0,
                        grid: { color: gridColor },
                        ticks: {
                            color: textColor,
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
    }
});
