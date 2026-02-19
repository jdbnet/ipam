document.addEventListener('DOMContentLoaded', function() {
    const navToggle = document.getElementById('nav-toggle');
    const mobileNav = document.getElementById('mobile-nav');
    const searchModal = document.getElementById('search-modal');
    const searchModalOpen = document.getElementById('search-modal-open');
    const searchModalOpenMobile = document.getElementById('search-modal-open-mobile');
    const searchModalClose = document.getElementById('search-modal-close');
    const searchModalBackdrop = document.getElementById('search-modal-backdrop');
    const searchModalInput = document.getElementById('search-modal-input');

    if (navToggle && mobileNav) {
        navToggle.addEventListener('click', function() {
            mobileNav.classList.toggle('hidden');
        });
    }

    function openSearchModal() {
        if (!searchModal) {
            return;
        }

        searchModal.classList.remove('hidden');
        searchModal.classList.add('flex');
        document.body.classList.add('overflow-hidden');

        if (mobileNav) {
            mobileNav.classList.add('hidden');
        }

        setTimeout(function() {
            if (searchModalInput) {
                searchModalInput.focus();
                searchModalInput.select();
            }
        }, 0);
    }

    function closeSearchModal() {
        if (!searchModal) {
            return;
        }

        searchModal.classList.add('hidden');
        searchModal.classList.remove('flex');
        document.body.classList.remove('overflow-hidden');
    }

    if (searchModalOpen) {
        searchModalOpen.addEventListener('click', openSearchModal);
    }

    if (searchModalOpenMobile) {
        searchModalOpenMobile.addEventListener('click', openSearchModal);
    }

    if (searchModalClose) {
        searchModalClose.addEventListener('click', closeSearchModal);
    }

    if (searchModalBackdrop) {
        searchModalBackdrop.addEventListener('click', closeSearchModal);
    }

    document.addEventListener('click', function(e) {
        if (mobileNav && navToggle && !mobileNav.contains(e.target) && !navToggle.contains(e.target)) {
            mobileNav.classList.add('hidden');
        }
    });

    document.addEventListener('keydown', function(e) {
        const target = e.target;
        const isEditableTarget = target && (
            target.tagName === 'INPUT' ||
            target.tagName === 'TEXTAREA' ||
            target.tagName === 'SELECT' ||
            target.isContentEditable
        );

        if (
            e.key === '/' &&
            !e.ctrlKey &&
            !e.metaKey &&
            !e.altKey &&
            searchModal &&
            !isEditableTarget
        ) {
            e.preventDefault();
            openSearchModal();
            return;
        }

        if (e.key === 'Escape') {
            closeSearchModal();
        }
    });
});