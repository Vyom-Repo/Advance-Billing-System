/**
 * static/js/landing.js
 * Advance Billing — Landing Page Interactions
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. FAQ Accordion
    const faqItems = document.querySelectorAll('.faq-item');
    faqItems.forEach(item => {
        const question = item.querySelector('.faq-question');
        if (question) {
            question.addEventListener('click', () => {
                const isActive = item.classList.contains('active');
                
                // Close all others
                faqItems.forEach(i => i.classList.remove('active'));
                
                // Toggle clicked
                if (!isActive) {
                    item.classList.add('active');
                }
            });
        }
    });

    // 2. Smooth Scroll for Anchor Links (About, Features, etc.)
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;
            
            const targetElement = document.querySelector(targetId);
            if (targetElement) {
                e.preventDefault();
                targetElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // 3. Navbar Scroll State
    const navbar = document.getElementById('navbar');
    if (navbar) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 20) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        });
    }

    // 4. Intersection Observer for Scroll Animations
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.15
    };
    
    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                // Optional: stop observing once animated
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    document.querySelectorAll('.animate-on-scroll, .invoice-mockup').forEach(el => {
        observer.observe(el);
    });

    // 5. 3D Parallax Tilt Effect on Product Showcase
    const mockup = document.querySelector('.invoice-mockup');
    if (mockup) {
        window.addEventListener('mousemove', (e) => {
            const rect = mockup.getBoundingClientRect();
            const mockupX = rect.left + rect.width / 2;
            const mockupY = rect.top + rect.height / 2;
            
            const mouseX = e.clientX - mockupX;
            const mouseY = e.clientY - mockupY;
            
            // Subtle tilt calculation
            const rotateX = (mouseY / (window.innerHeight / 2)) * -8;
            const rotateY = (mouseX / (window.innerWidth / 2)) * 8;
            
            mockup.style.transform = `perspective(1600px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(0.98)`;
        });
        
        window.addEventListener('mouseleave', () => {
            mockup.style.transform = `perspective(1600px) rotateX(10deg) rotateY(0deg) scale(0.96)`;
        });
    }

    // 6. Spotlight Cursor Tracking for Cards
    const cards = document.querySelectorAll('.card-hover');
    cards.forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            card.style.setProperty('--mouse-x', `${x}px`);
            card.style.setProperty('--mouse-y', `${y}px`);
        });
    });

    // 7. Mobile Menu Toggle
    const mobileBtn = document.getElementById('mobile-menu-btn');
    const navLinks = document.querySelector('.nav-links');
    if (mobileBtn && navLinks) {
        mobileBtn.addEventListener('click', () => {
            if (navLinks.style.display === 'flex') {
                navLinks.style.display = 'none';
            } else {
                navLinks.style.display = 'flex';
                navLinks.style.flexDirection = 'column';
                navLinks.style.position = 'absolute';
                navLinks.style.top = '100%';
                navLinks.style.left = '0';
                navLinks.style.right = '0';
                navLinks.style.background = 'rgba(13, 13, 20, 0.95)';
                navLinks.style.backdropFilter = 'blur(24px)';
                navLinks.style.padding = 'var(--space-6)';
                navLinks.style.borderRadius = 'var(--radius-lg)';
                navLinks.style.border = '1px solid rgba(255, 157, 46, 0.2)';
            }
        });
    }
});
