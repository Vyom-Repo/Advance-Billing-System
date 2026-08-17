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
    // The theme is primarily handled by the server (Django session + context processor),
    // but this function allows client-side preview before saving to backend.
    window.setTheme = function(themeId) {
        document.documentElement.setAttribute('data-theme', themeId);
        // In a full implementation, you would also POST to a Django view to save to session.
    };
});
