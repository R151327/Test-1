/*global gettext*/
(function() {
    'use strict';
    window.addEventListener('load', function() {
        // Add anchor tag for Show/Hide link
        const fieldsets = document.querySelectorAll('fieldset.collapse');
        for (let i = 0; i < fieldsets.length; i++) {
            const elem = fieldsets[i];
            // Don't hide if fields in this fieldset have errors
            if (elem.querySelectorAll('div.errors, ul.errorlist').length === 0) {
                elem.classList.add('collapsed');
                const h2 = elem.querySelector('h2');
                const link = document.createElement('a');
                link.id = 'fieldsetcollapser' + i;
                link.className = 'collapse-toggle';
                link.href = '#';
                link.textContent = gettext('Show');
                h2.appendChild(document.createTextNode(' ('));
                h2.appendChild(link);
                h2.appendChild(document.createTextNode(')'));
            }
        }
        // Add toggle to hide/show anchor tag
        const toggleFunc = function(ev) {
            if (ev.target.matches('.collapse-toggle')) {
                ev.preventDefault();
                ev.stopPropagation();
                const fieldset = ev.target.closest('fieldset');
                if (fieldset.classList.contains('collapsed')) {
                    // Show
                    ev.target.textContent = gettext('Hide');
                    fieldset.classList.remove('collapsed');
                } else {
                    // Hide
                    ev.target.textContent = gettext('Show');
                    fieldset.classList.add('collapsed');
                }
            }
        };
        const inlineDivs = document.querySelectorAll('fieldset.module');
        for (let i = 0; i < inlineDivs.length; i++) {
            inlineDivs[i].addEventListener('click', toggleFunc);
        }
    });
})();
