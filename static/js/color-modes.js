(() => {
    'use strict'

    const storedTheme = localStorage.getItem('theme')
    const getPreferredTheme = () => {
        if (storedTheme) {
            return storedTheme
        }
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }

    const setTheme = (theme) => {
        if (theme === 'auto') {
            document.documentElement.removeAttribute('data-bs-theme')
        } else {
            document.documentElement.setAttribute('data-bs-theme', theme)
        }
    }

    // Initialize
    const theme = getPreferredTheme()
    setTheme(theme)

    // Dropdown buttons
    const btns = document.querySelectorAll('[data-bs-theme-value]')
    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            const val = btn.getAttribute('data-bs-theme-value')
            localStorage.setItem('theme', val)
            setTheme(val)

            // update active states in dropdown
            btns.forEach(b => b.classList.remove('active'))
            btn.classList.add('active')
        })
    })
})();
