// 全局状态
const state = {
    page: 1,
    size: 15,
    filter: "all", // all | unread | starred
    totalPages: 1,
};

const API_BASE = "/articles";

// 工具函数

// 格式化时间
function formatDate(isoString) {
    if (!isoString) return "";
    const d = new Date(isoString);
    return d.toLocaleString("zh-CN", {
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit"
    });
}

// 拉取数据
async function fetchArticles() {
    const container = document.getElementById("articles-container");
    container.innerHTML = `<div class="text-center p-5 text-muted">加载中...</div>`;

    // 1. 构造查询参数
    const params = new URLSearchParams({
        page: state.page,
        size: state.size,
    });
    if (state.filter === "unread") params.append("is_read", "false");
    if (state.filter === "starred") params.append("is_starred", "true");

    try{
        // 2. 请求 API
        const res = await fetch(`${API_BASE}?${params.toString()}`);
        if (!res.ok) throw new Error("网络请求失败");

        const data = await res.json();
        state.totalPages = data.meta.pages;

        // 3. 渲染
        renderArticles(data.items);
        renderPagination(data.meta);

    } catch (err) {
        container.innerHTML = `<div class="alert alert-danger m-3">加载失败：${err.message}</div>`;
    }
}

// 渲染列表
function renderArticles(items) {
    const container = document.getElementById("articles-container");

    if (items.length === 0) {
        container.innerHTML = `<div class="text-center p-5 text-muted">没有符合条件的文章 🎉</div>`;
        return;
    }

    let html = "";
    for (const item of items) {
        const statusClass = item.is_read ? "read" : "unread";
        const starIcon = item.is_starred ? "bi-star-fill text-warning" : "bi-star";
        const isReadIcon = item.is_read ? 'bi-envelope' : 'bi-envelope-open';
        const isReadTitle = item.is_read ? '标为未读' : '标为已读';
        html += `
            <div class="feed-item ${statusClass} p-3 d-flex justify-content-between align-items-center" id="article-${item.id}">
                <div class="me-3 flex-grow-1">
                    <div class="mb-1 text-muted small>
                        <span class="badge bg-secondary">${item.feed_title || "未知源"}</span>
                        <span class="ms-2"><i class="bi bi-clock"></i>${formatDate(item.published_at || item.fetched_at)}</span>
                    </div>
                    <a href="#" class="feed-title d-block text-truncate mb-1" style="max-width: 800px;" onclick="openArticle(${item.id}, event)">
                        ${item.title}
                    </a>
                    <div class="text-muted small text-truncate" style="max-width: 800px;">
                        ${item.summary || "无摘要"}
                    </div>
                </div>
                <div class="d-flex gap-2">
                    <!-- 收藏按钮 -->
                    <button class="btn btn-sm btn-light border-0" onclick="toggleStar(${item.id}, ${!item.is_starred})">
                        <i class="bi ${starIcon}"></i>
                    </button>
                    <!-- 标记已读按钮 -->
                    <button class="btn btn-sm btn-light border-0" onclick="toggleRead(${item.id}, ${!item.is_read})" title="${isReadTitle}">
                        <i class="bi ${isReadIcon}"></i>
                    </button>
                </div>
            </div>
        `;
    }
    container.innerHTML = html;
}

// 渲染分页
function renderPagination(meta) {
    const nav = document.getElementById("pagination");
    if (meta.pages <= 1) {
        nav.innerHTML = "";
        return;
    }

    let html = "";
    // 上一页
    html += `
        <li class="page-item ${meta.has_prev ? "" : "disabled"}">
            <a class="page-link" href="#" onclick="changePage(${meta.page - 1})">上一页</a>
        </li>
    `;

    // 当前页
    html += `<li class="page-item disabled"><span class="page-link">${meta.page} / ${meta.pages}</span></li>`;

    // 下一页
    html += `
        <li class="page-item ${meta.has_next ? "" : "disabled"}">
            <a class="page-link" href="#" onclick="changePage(${meta.page + 1})">下一页</a>
        </li>
    `;
    nav.innerHTML = html;
}

// 交互操作
// 详情弹窗
let articleModalInstance = null;

async function openArticle(id, event) {
    console.log("id = ", id);
    if (event) event.preventDefault();

    // 1. 初始化 Modal 实例
    if (!articleModalInstance) {
        articleModalInstance = new bootstrap.Modal(document.getElementById('articleModal'));
    }

    const titleEl = document.getElementById("modal-title");
    const bodyEl = document.getElementById("modal-body");
    const metaEl = document.getElementById("modal-meta");
    const linkEl = document.getElementById("modal-link");
    const exportBtn = document.getElementById("modal-export-btn");
    exportBtn.href = `${API_BASE}/${id}/export`;

    titleEl.innerText = "加载中...";
    bodyEl.innerHTML = `<div class="text-center py-5"><span class="spinner-border"></span></div>`;
    articleModalInstance.show();

    try{
        // 2. 请求详情接口
        const res = await fetch(`${API_BASE}/${id}`);
        if (!res.ok) throw new Error("获取详情失败");
        const data = await res.json();

        titleEl.innerText = data.title;
        metaEl.innerText = `来自 ${data.feed_title} | ${formatDate(data.published_at || data.fetched_at)}`;
        linkEl.href = data.link;

        // 3. 渲染正文
        let contentHtml = ""

        if (data.ai_summary) {
            contentHtml += `
                <div class="alert alert-info border-info mb-4" style="background-color: #f0f8ff;">
                    <h6 class="alert-heading fw-bold"><i class="bi bi-stars"></i> AI 智能摘要</h6>
                    <p class="mb-0">${data.ai_summary}</p>
                </div>
            `;
        }
        const isProbablySummary = !data.content || data.content.length < 500;

        if (isProbablySummary && data.link) {
            contentHtml += `
                <div id="extract-btn-container" class="text-center my-4 py-4 bg-light rounded border">
                    <p class="text-muted mb-3">当前 RSS 源只提供了摘要。你可以尝试从原网页抓取完整正文。</p>
                    <button class="btn btn-primary" onclick="extractFullText(${data.id})">
                        <i class="bi bi-box-arrow-in-down"></i> 抓取完整正文
                    </button>
                </div>
            `;
            contentHtml += `<div class="text-muted mt-3" style="font-size: 0.9rem;">${data.summary || ""}</div>`;
        } else {
            contentHtml += data.content || "<p class='text-muted'>暂无正文</p>";
        }
        
        bodyEl.innerHTML = contentHtml;

        // 4. 如果未读，自动标记为已读并刷新列表
        if(!data.is_read) {
            await toggleRead(id, true);
        }
    } catch (err) {
        bodyEl.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
    }
}

function changePage(page) {
    if (page < 1 || page > state.totalPages) return;
    state.page = page;
    fetchArticles();
    window.scrollTo(0, 0) // 翻页后回到顶部
}

async function toggleStar(id, newState) {
    await fetch(`${API_BASE}/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_starred: newState })
    });
    fetchArticles(); // 重新拉取
}

async function toggleRead(id, newState) {
    await fetch(`${API_BASE}/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_read: newState })
    });
    fetchArticles();
}

// 视图切换

function showListView() {
    document.getElementById("view-nav").querySelector(".nav-link").classList.remove("active");
    document.getElementById("view-nav").querySelector(".nav-link").classList.add("link-dark");

    document.getElementById("dashboard-container").classList.add("d-none");
    document.getElementById("articles-container").classList.remove("d-none");
    document.getElementById("pagination").classList.remove("d-none");
    document.getElementById("page-title").innerText = "全部文章";

    // 如果从看板切回来，刷新列表
    fetchArticles();
}

function showDashboardView() {
    document.getElementById("view-nav").querySelector(".nav-link").classList.add("active");
    document.getElementById("view-nav").querySelector(".nav-link").classList.remove("link-dark");

    // 隐藏侧边栏的筛选高亮
    document.querySelectorAll("#filter-nav .nav-link").forEach(n => {
        n.classList.remove("active");
        n.classList.add("link-dark");
    });

    document.getElementById("articles-container").classList.add("d-none");
    document.getElementById("pagination").classList.add("d-none");
    document.getElementById("dashboard-container").classList.remove("d-none");
    document.getElementById("page-title").innerText = "数据看板";

    fetchAndRenderDashboard();
}

// 看板图表

let pieChartInstance = null;
let barChartInstance = null;

async function fetchAndRenderDashboard() {
    try{
        const res = await fetch("/articles/stats");
        if (!res.ok) throw new Error("获取统计数据失败");
        const data = await res.json();

        renderPieChart(data.per_feed);
        renderBarChart(data);
    } catch (err) {
        alert(err.message);
    }
}

function renderPieChart(perFeed) {
    const ctx = document.getElementById("pieChart").getContext("2d");

    if (pieChartInstance) pieChartInstance.destroy();

    // 标签和数据
    const labels = perFeed.map(x => x.feed_title || "未知源");
    const counts = perFeed.map(x => x.count);

    if (labels.length === 0) {
        labels.push("暂无数据");
        counts.push(1);
    }
    
    pieChartInstance = new Chart(ctx, {
        type: "doughnut", // 环形图
        data: {
            labels: labels,
            datasets: [{
                data: counts,
                backgroundColor: [
                    "#0d6efd", "#198754", "#ffc107", "#dc3545", "#6f42c1", "#fd7e14"
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "bottom" }
            }
        }
    });
}

function renderBarChart(stats) {
    const ctx = document.getElementById("barChart").getContext("2d");
    if (barChartInstance) barChartInstance.destroy();

    const unread = stats.unread;
    const read = stats.total - stats.unread;

    barChartInstance = new Chart(ctx, {
        type: "bar",
        data: {
            labels: ["总文章", "已读", "未读", "收藏"],
            datasets: [{
                label: "文章数量",
                data: [stats.total, read, unread, stats.starred],
                backgroundColor: [
                    "#6c757d", "#198754", "#0d6efd", "#ffc107"
                ],
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { beginAtZero: true, ticks: { stepSize: 5 } }
            }
        }
    });
}

async function fetchSyncStatus() {
    try{
        const res = await fetch("/feeds/scheduler/status");
        if (!res.ok) return;
        const data = await res.json();

        const badge = document.getElementById("sync-status");
        if (data.last_fetched_at) {
            const timeStr = formatDate(data.last_fetched_at);
            badge.innerHTML = `<i class="bi bi-check-circle text-success"></i> 上次同步：${timeStr}`;
        } else {
            badge.innerHTML = `<i class="bi bi-exclamation-circle text-warning"></i> 尚未同步过`;
        }
    } catch (err) {
        console.error("获取同步状态失败", err);
    }
}


async function extractFullText(id) {
    const btnContainer = document.getElementById("extract-btn-container");
    const bodyEl = document.getElementById("modal-body");

    btnContainer.innerHTML = `
        <div class="spinner-border text-primary mb-2" role="status"></div>
        <p class="text-muted mb-0">正在分析网页结构并提取正文，请稍后...</p>
    `;

    try {
        const res = await fetch(`${API_BASE}/${id}/extract`, { method: "POST" });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "抓取失败");
        }

        const data = await res.json();

        let newHtml = "";
        if (data.ai_summary) {
            newHtml += `
                <div class="alert alert-info border-info mb-4" style="background-color: #f0f8ff;">
                    <h6 class="alert-heading fw-bold"><i class="bi bi-stars"></i> AI 智能摘要</h6>
                    <p class="mb-0">${data.ai_summary}</p>
                </div>
            `;
        }
        newHtml += data.content;
        bodyEl.innerHTML = newHtml;
        fetchArticles();
    } catch (err) {
        btnContainer.innerHTML = `
            <div class="alert alert-danger mb-0">
                <i class="bi bi-x-circle"></i> ${err.message}
                <button class="btn btn-sm btn-outline-danger ms-3" onclick="extractFullText(${id})">重试</button>
            </div>   
        `;
    }
}

// 初始化与事件绑定

document.addEventListener("DOMContentLoaded", () => {
    // 初始加载
    fetchArticles();
    // 同步状态
    fetchSyncStatus();

    // 绑定侧边栏筛选点击
    document.querySelectorAll("#filter-nav .nav-link").forEach(el => {
        el.addEventListener("click", (e) => {
            e.preventDefault();

            // 切换样式
            document.querySelectorAll("#filter-nav .nav-link").forEach(n => {
                n.classList.remove("active");
                n.classList.add("link-dark");
            });
            el.classList.add("active");
            el.classList.remove("link-dark");

            // 更新状态并请求
            state.filter = el.dataset.filter;
            state.page = 1;

            document.getElementById("dashboard-container").classList.add("d-none");
            document.getElementById("articles-container").classList.remove("d-none");
            document.getElementById("pagination").classList.remove("d-none");
            document.getElementById("view-nav").querySelector(".nav-link").classList.remove("active");

            const titles = { all: "全部文章", unread: "未读文章", starred: "收藏文章" };
            document.getElementById("page-title").innerText = titles[state.filter];

            fetchArticles();
        });
    });

    // 绑定刷新抓取按钮
    document.getElementById("btn-refresh").addEventListener("click", async (e) => {
        const btn = e.currentTarget;
        const origHtml = btn.innerHTML;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> 抓取中...`;
        btn.disabled = true;

        try{
            await fetch("/feeds/scheduler/run-now", { method: "POST" });
            alert("后台抓取任务已触发，稍等几秒后刷新页面看看！");
            // 延迟几秒后更新状态条
            setTimeout(fetchSyncStatus, 3000);
        } catch (err) {
            alert("触发失败");
        } finally {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    });

    // 绑定一键已读按钮
    document.getElementById("btn-mark-all-read").addEventListener("click", async (e) => {
        if (!confirm("确定要把所有文章标记为已读吗？")) return;

        const btn = e.currentTarget;
        const origHtml = btn.innerHTML;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> 处理中...`;
        btn.disabled = true;

        try{
            const res = await fetch(`/articles/mark-all-read`, { method: "POST" });
            const data = await res.json();
            alert(`已标记 ${data.updated} 篇文章为已读`);
            fetchArticles();
        } catch (err) {
            alert("操作失败");
        } finally {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    });

    // 绑定看板切换
    document.getElementById("nav-dashboard").addEventListener("click", (e) => {
        e.preventDefault();
        showDashboardView();
    });
});
