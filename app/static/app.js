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
        bodyEl.innerHTML = data.content || data.summary || "<p class='text-muted'>暂无正文</p>";

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

// 初始化与事件绑定

document.addEventListener("DOMContentLoaded", () => {
    // 初始加载
    fetchArticles();

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
});
