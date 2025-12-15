// app/static/js/app.js

document.addEventListener('DOMContentLoaded', () => {
    console.log('✅ FastAPI Base Template Loaded');
    console.log('📍 Current path:', window.location.pathname);

    const main = document.querySelector('main');
    if (!main) return;

    // infoBar는 개발용이면 유지, 싫으면 삭제해도 됨
    const infoBar = document.createElement('div');
    infoBar.style.marginTop = '12px';
    infoBar.style.padding = '8px 12px';
    infoBar.style.background = '#f3f4f6';
    infoBar.style.borderRadius = '8px';

    try {
        main.prepend(infoBar);
    } catch (e) {
        console.warn('infoBar prepend 실패:', e);
    }
});
