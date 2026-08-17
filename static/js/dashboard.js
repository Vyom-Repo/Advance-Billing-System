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

    // 3. Initialize Chart.js Placeholder (if canvas exists)
    const chartCanvas = document.getElementById('revenueChart');
    if (chartCanvas && typeof Chart !== 'undefined') {
        const ctx = chartCanvas.getContext('2d');
        
        // Get primary accent color from CSS variables
        const computedStyle = getComputedStyle(document.documentElement);
        const accentColor = computedStyle.getPropertyValue('--palette-accent-400').trim() || '#ff9933';
        const gridColor = computedStyle.getPropertyValue('--color-border').trim() || 'rgba(255, 255, 255, 0.1)';
        const textColor = computedStyle.getPropertyValue('--color-text-secondary').trim() || '#9494b8';

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
                datasets: [{
                    label: 'Revenue',
                    data: [12000, 19000, 15000, 22000, 28000, 24000],
                    borderColor: accentColor,
                    backgroundColor: `${accentColor}33`, // 20% opacity
                    borderWidth: 3,
                    tension: 0.4,
                    fill: true,
                    pointBackgroundColor: accentColor,
                    pointBorderColor: '#fff',
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
                        bodyColor: '#fff',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        padding: 10
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: textColor }
                    },
                    y: {
                        grid: { color: gridColor },
                        ticks: { color: textColor, callback: (value) => '₹' + (value/1000) + 'k' }
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
