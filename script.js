// Google Home Page Clone - JavaScript functionality

document.addEventListener('DOMContentLoaded', function() {
    // Focus the search input on page load
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
        searchInput.focus();
    }

    // Handle search box focus effects
    const searchBox = document.querySelector('.search-box');
    if (searchBox && searchInput) {
        searchInput.addEventListener('focus', function() {
            searchBox.classList.add('focused');
        });

        searchInput.addEventListener('blur', function() {
            searchBox.classList.remove('focused');
        });
    }

    // Handle microphone icon click (placeholder for voice search)
    const micIcon = document.querySelector('.mic-icon');
    if (micIcon) {
        micIcon.addEventListener('click', function() {
            alert('Voice search would be activated here');
        });
    }

    // Handle search form submission
    const searchForm = document.querySelector('.search-container');
    if (searchForm && searchInput) {
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const query = searchInput.value.trim();
                if (query) {
                    // In a real implementation, this would redirect to Google search
                    console.log('Search query:', query);
                    alert('Searching for: ' + query);
                }
            }
        });
    }

    // Handle button clicks
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(button => {
        button.addEventListener('click', function() {
            const query = searchInput ? searchInput.value.trim() : '';
            if (query) {
                console.log('Button clicked:', button.textContent, 'Query:', query);
                alert(button.textContent + ' for: ' + query);
            } else {
                alert('Please enter a search query first');
            }
        });
    });

    // Handle header links
    const headerLinks = document.querySelectorAll('.header-links a');
    headerLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Header link clicked:', this.textContent);
        });
    });

    // Handle footer links
    const footerLinks = document.querySelectorAll('.footer-links a');
    footerLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Footer link clicked:', this.textContent);
        });
    });

    // Handle apps icon click
    const appsIcon = document.querySelector('.apps-icon');
    if (appsIcon) {
        appsIcon.addEventListener('click', function() {
            alert('Google apps menu would open here');
        });
    }

    // Handle sign in button
    const signinBtn = document.querySelector('.signin-btn');
    if (signinBtn) {
        signinBtn.addEventListener('click', function() {
            alert('Sign in page would open here');
        });
    }
});