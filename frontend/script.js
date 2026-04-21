// Dark Mode Toggle
const themeToggleBtn = document.getElementById('themeToggle');
themeToggleBtn.addEventListener('click', function() {
    document.documentElement.classList.toggle('dark');
});

// Tab Switcher
let currentMode = 'file';
function switchTab(mode) {
    currentMode = mode;
    const tabFile = document.getElementById('tabFile');
    const tabUrl = document.getElementById('tabUrl');
    const areaFile = document.getElementById('areaFile');
    const areaUrl = document.getElementById('areaUrl');

    if (mode === 'file') {
        tabFile.className = "py-2 px-4 border-b-2 border-blue-600 text-blue-600 font-semibold transition";
        tabUrl.className = "py-2 px-4 border-b-2 border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition";
        areaFile.classList.remove('hidden');
        areaFile.classList.add('flex');
        areaUrl.classList.add('hidden');
    } else {
        tabUrl.className = "py-2 px-4 border-b-2 border-blue-600 text-blue-600 font-semibold transition";
        tabFile.className = "py-2 px-4 border-b-2 border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 transition";
        areaUrl.classList.remove('hidden');
        areaFile.classList.remove('flex');
        areaFile.classList.add('hidden');
    }
}

document.getElementById('videoFile').addEventListener('change', function(e) {
    document.getElementById('fileNameDisplay').textContent = e.target.files[0] ? e.target.files[0].name : "Tối đa 50MB";
});

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    const bg = type === 'success' ? 'bg-emerald-500' : 'bg-red-600';
    toast.className = `${bg} text-white px-5 py-3 rounded shadow-lg transition-all duration-300 transform translate-x-0 flex items-center font-medium`;
    toast.innerHTML = type === 'error' ? `<i class="fa-solid fa-triangle-exclamation mr-2"></i> ${message}` : message;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3500);
}

document.getElementById('uploadForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const formData = new FormData();
    
    // Thu thập file hoặc URL
    if (currentMode === 'file') {
        const file = document.getElementById('videoFile').files[0];
        if (!file) return showToast("Vui lòng tải file lên!", "error");
        formData.append('video', file);
    } else {
        const url = document.getElementById('videoUrl').value.trim();
        if (!url) return showToast("Vui lòng dán URL!", "error");
        formData.append('video_url', url);
    }

    // Thu thập thông số
    formData.append('sys_password', document.getElementById('sysPassword').value.trim()); // Gửi mật khẩu xuống API
    formData.append('api_key', document.getElementById('apiKey').value.trim());
    formData.append('style', document.getElementById('subStyle').value);

    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('submitBtn').disabled = true;

    try {
        const response = await fetch('/run-tool', { method: 'POST', body: formData });
        const result = await response.json();

        // 🚨 Xử lý riêng lỗi sai mật khẩu (HTTP 401)
        if (response.status === 401) {
            showToast(result.detail, "error");
            document.getElementById('sysPassword').value = ''; // Xóa trắng pass sai
            document.getElementById('sysPassword').focus();
            return;
        }

        if (response.ok && result.status === 'success') {
            document.getElementById('viSub').value = result.data.vi_srt;
            document.getElementById('zhSub').value = result.data.zh_srt;
            
            if (result.data.video_url) {
                const player = document.getElementById('player');
                player.src = result.data.video_url;
                document.getElementById('videoPreview').classList.remove('hidden');
            }

            document.getElementById('resultArea').classList.remove('hidden');
            showToast("Bóc băng thành công!");
            document.getElementById('resultArea').scrollIntoView({ behavior: 'smooth' });
        } else {
            showToast(result.detail || "Có lỗi từ máy chủ", "error");
        }
    } catch (error) {
        showToast("Mất kết nối tới Server. Vui lòng thử lại.", "error");
    } finally {
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('submitBtn').disabled = false;
    }
});

function downloadFile(elementId, filename) {
    let text = document.getElementById(elementId).value;
    if (!text) return showToast("Chưa có dữ liệu!", "error");
    
    if (filename.endsWith('.txt')) {
        text = text.replace(/^\d+$/gm, '').replace(/^\d{2}:\d{2}:\d{2},\d{3}.*$/gm, '').replace(/^\s*[\r\n]/gm, '').trim();
    }
    
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    a.click(); URL.revokeObjectURL(url);
}