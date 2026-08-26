/**
 * static/js/main.js
 * Advance Billing — Global JavaScript
 * 
 * Handles theme initialization and global UI interactions (e.g. flash messages).
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Icons (Lucide)
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // 2. Handle Flash Messages Auto-dismiss
    const flashMessages = document.querySelectorAll('.alert');
    flashMessages.forEach(msg => {
        const closeBtn = msg.querySelector('.alert__close');
        
        // Setup close button
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                msg.style.opacity = '0';
                setTimeout(() => msg.remove(), 300);
            });
        }
        
        // Auto dismiss after 5 seconds if not an error
        if (!msg.classList.contains('alert-error')) {
            setTimeout(() => {
                if (msg.parentElement) {
                    msg.style.opacity = '0';
                    msg.style.transition = 'opacity 0.3s ease';
                    setTimeout(() => msg.remove(), 300);
                }
            }, 5000);
        }
    });

    // 4. Global Master Loader Controller API
    const appLoader = document.getElementById('app-loader');
    
    window.AdvanceBillingLoader = {
        show: function(customTagline) {
            if (appLoader) {
                if (customTagline) {
                    const taglineEl = appLoader.querySelector('.loader-tagline');
                    if (taglineEl) taglineEl.textContent = customTagline;
                }
                appLoader.classList.remove('fade-out');
            }
        },
        hide: function() {
            if (appLoader) {
                appLoader.classList.add('fade-out');
            }
        }
    };

    // Auto-hide page startup loader smoothly after DOM ready
    setTimeout(() => {
        window.AdvanceBillingLoader.hide();
    }, 250);

    // 5. Button Loading States for Form Submissions
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // Report validity if invalid and stop submission
            if (form.checkValidity && !form.checkValidity()) {
                form.reportValidity();
                return;
            }
            
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                const originalText = submitBtn.innerText || submitBtn.value;
                let loadingText = 'Processing...';
                
                // Contextual text mapping
                const lowerText = originalText.toLowerCase();
                if (lowerText.includes('sign in') || lowerText.includes('log in')) {
                    loadingText = 'Signing In...';
                } else if (lowerText.includes('sign up') || lowerText.includes('register') || lowerText.includes('create account')) {
                    loadingText = 'Creating Account...';
                } else if (lowerText.includes('send') || lowerText.includes('resend')) {
                    loadingText = 'Sending...';
                } else if (lowerText.includes('save') || lowerText.includes('update')) {
                    loadingText = 'Saving...';
                } else if (lowerText.includes('invoice')) {
                    loadingText = 'Generating Invoice...';
                }

                // Apply button loading state asynchronously so native submission is not aborted
                setTimeout(() => {
                    submitBtn.disabled = true;
                    submitBtn.style.opacity = '0.75';
                    submitBtn.style.cursor = 'wait';
                    if (submitBtn.tagName === 'INPUT') {
                        submitBtn.value = loadingText;
                    } else {
                        submitBtn.innerText = loadingText;
                    }
                }, 0);
            }
        });
    });

    // 3. Theme Toggle Support (Optional UI hook)
    window.setTheme = function(themeId) {
        document.documentElement.setAttribute('data-theme', themeId);
    };

    // 6. User Menu & Notification Dropdown Handlers
    function getCsrfToken() {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, 10) === ('csrftoken=')) {
                    cookieValue = decodeURIComponent(cookie.substring(10));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const userMenuBtn = document.getElementById('user-menu-btn');
    const userMenuDropdown = document.getElementById('user-menu-dropdown');
    
    if (userMenuBtn && userMenuDropdown) {
        userMenuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isShown = userMenuDropdown.classList.contains('show');
            closeAllDropdowns();
            if (!isShown) {
                userMenuDropdown.classList.add('show');
                userMenuBtn.setAttribute('aria-expanded', 'true');
            }
        });
    }

    const bellBtn = document.getElementById('notification-bell-btn');
    const notifDropdown = document.getElementById('notification-dropdown');
    const notifBadge = document.getElementById('notification-badge');
    const notifList = document.getElementById('notification-list');
    const markAllBtn = document.getElementById('mark-all-read-btn');

    function closeAllDropdowns() {
        if (userMenuDropdown) {
            userMenuDropdown.classList.remove('show');
            if (userMenuBtn) userMenuBtn.setAttribute('aria-expanded', 'false');
        }
        if (notifDropdown) {
            notifDropdown.classList.remove('show');
            if (bellBtn) bellBtn.setAttribute('aria-expanded', 'false');
        }
    }

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.notification-menu') && !e.target.closest('.user-menu')) {
            closeAllDropdowns();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAllDropdowns();
        }
    });

    function updateBadgeCount(count) {
        if (!notifBadge) return;
        if (count > 0) {
            notifBadge.textContent = count > 99 ? '99+' : count;
            notifBadge.style.display = 'inline-flex';
        } else {
            notifBadge.style.display = 'none';
        }
    }

    function fetchNotifications() {
        if (!notifList) return;
        fetch('/api/notifications/', {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(res => res.json())
        .then(data => {
            updateBadgeCount(data.unread_count);
            renderNotificationList(data.notifications || []);
        })
        .catch(err => {
            console.error('Failed to fetch notifications:', err);
            notifList.innerHTML = '<div class="notification-empty"><div class="notification-empty-desc">Could not load notifications.</div></div>';
        });
    }

    function renderNotificationList(items) {
        if (!notifList) return;
        if (items.length === 0) {
            notifList.innerHTML = `
                <div class="notification-empty">
                    <div class="notification-empty-title">All caught up!</div>
                    <div class="notification-empty-desc">You have no notifications right now.</div>
                </div>
            `;
            return;
        }

        notifList.innerHTML = items.map(item => {
            const unreadClass = item.is_read ? '' : 'unread';
            const iconName = item.icon || 'bell';
            const targetUrl = item.target_url || '';
            return `
                <div class="notification-item ${unreadClass}" data-id="${item.id}" data-url="${targetUrl}">
                    <div class="notification-icon-box">
                        <i data-lucide="${iconName}" style="width: 16px; height: 16px;"></i>
                    </div>
                    <div class="notification-content">
                        <div class="notification-item-title">${escapeHtml(item.title)}</div>
                        <div class="notification-item-message">${escapeHtml(item.message)}</div>
                        <div class="notification-item-time">${escapeHtml(item.timesince)}</div>
                    </div>
                </div>
            `;
        }).join('');

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }

        const notifElements = notifList.querySelectorAll('.notification-item');
        notifElements.forEach(el => {
            el.addEventListener('click', (e) => {
                const notifId = el.getAttribute('data-id');
                const targetUrl = el.getAttribute('data-url');
                
                fetch(`/api/notifications/${notifId}/read/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                .then(res => res.json())
                .then(resData => {
                    el.classList.remove('unread');
                    if (typeof resData.unread_count !== 'undefined') {
                        updateBadgeCount(resData.unread_count);
                    }
                    if (targetUrl) {
                        window.location.href = targetUrl;
                    }
                })
                .catch(() => {
                    if (targetUrl) {
                        window.location.href = targetUrl;
                    }
                });
            });
        });
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, "&amp;")
                  .replace(/</g, "&lt;")
                  .replace(/>/g, "&gt;")
                  .replace(/"/g, "&quot;")
                  .replace(/'/g, "&#039;");
    }

    if (bellBtn && notifDropdown) {
        bellBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isShown = notifDropdown.classList.contains('show');
            closeAllDropdowns();
            if (!isShown) {
                notifDropdown.classList.add('show');
                bellBtn.setAttribute('aria-expanded', 'true');
                fetchNotifications();
            }
        });
    }

    if (markAllBtn) {
        markAllBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            fetch('/api/notifications/read-all/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(res => res.json())
            .then(data => {
                updateBadgeCount(0);
                const items = notifList.querySelectorAll('.notification-item');
                items.forEach(item => item.classList.remove('unread'));
            })
            .catch(err => console.error('Failed to mark all as read:', err));
        });
    }
});
