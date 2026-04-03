// ========================================
// 喫茶店 在庫管理 - データストア (localStorage)
// ========================================

const DEFAULT_ITEMS = [
    { name: "いちご", qty: 3, unit: "パック", category: "食材", alert: "要注意", dot: "red", badge: "期限近", badgeClass: "badge-expiry", minStock: 2, expiry: "2〜3日", group: "日配品", stocked: "4/1", stockedBy: "マスター" },
    { name: "生クリーム", qty: 2, unit: "パック", category: "食材", alert: "要注意", dot: "yellow", badge: "残少", badgeClass: "badge-low", minStock: 3, expiry: "5日前後", group: "日配品", stocked: "3/30", stockedBy: "バイト１" },
    { name: "モカ豆", qty: 1, unit: "kg", category: "コーヒー豆", alert: "要注意", dot: "yellow", badge: "残少", badgeClass: "badge-low", minStock: 2, expiry: "約180日", group: "コーヒー豆", stocked: "3/15", stockedBy: "マスター" },
    { name: "ミネラルウォーター", qty: 2, unit: "本", category: "食材", alert: "要注意", dot: "red", badge: "要発注", badgeClass: "badge-expiry", minStock: 5, expiry: "約365日", group: "飲料", stocked: "2/10", stockedBy: "バイト２" },
    { name: "コーヒーフィルター", qty: 20, unit: "枚", category: "消耗品", alert: "要注意", dot: "yellow", badge: "残少", badgeClass: "badge-low", minStock: 30, expiry: "なし", group: "消耗品", stocked: "3/20", stockedBy: "バイト１" },
    { name: "牛乳", qty: 3, unit: "本", category: "食材", alert: "", dot: "green", badge: "", badgeClass: "", minStock: 2, expiry: "1週間", group: "日配品", stocked: "3/31", stockedBy: "マスター" },
    { name: "ブラジル豆", qty: 3, unit: "kg", category: "コーヒー豆", alert: "", dot: "green", badge: "", badgeClass: "", minStock: 1, expiry: "約180日", group: "コーヒー豆", stocked: "3/1", stockedBy: "マスター" },
    { name: "コロンビア豆", qty: 2, unit: "kg", category: "コーヒー豆", alert: "", dot: "green", badge: "", badgeClass: "", minStock: 1, expiry: "約180日", group: "コーヒー豆", stocked: "3/5", stockedBy: "バイト２" },
    { name: "ブレンド豆", qty: 4, unit: "kg", category: "コーヒー豆", alert: "", dot: "green", badge: "", badgeClass: "", minStock: 1, expiry: "約180日", group: "コーヒー豆", stocked: "3/10", stockedBy: "マスター" },
    { name: "小麦粉", qty: 2, unit: "kg", category: "食材", alert: "", dot: "green", badge: "", badgeClass: "", minStock: 1, expiry: "約180日", group: "製菓材料", stocked: "3/1", stockedBy: "バイト１" },
    { name: "砂糖", qty: 3, unit: "kg", category: "食材", alert: "", dot: "green", badge: "", badgeClass: "", minStock: 1, expiry: "約365日", group: "製菓材料", stocked: "2/15", stockedBy: "マスター" },
    { name: "紙ナプキン", qty: 5, unit: "袋", category: "消耗品", alert: "", dot: "green", badge: "", badgeClass: "", minStock: 2, expiry: "なし", group: "消耗品", stocked: "3/25", stockedBy: "バイト２" },
    { name: "ストロー", qty: 2, unit: "箱", category: "消耗品", alert: "", dot: "green", badge: "", badgeClass: "", minStock: 1, expiry: "なし", group: "消耗品", stocked: "3/15", stockedBy: "マスター" },
    { name: "砂糖の小袋", qty: 3, unit: "箱", category: "消耗品", alert: "", dot: "green", badge: "", badgeClass: "", minStock: 1, expiry: "なし", group: "消耗品", stocked: "3/20", stockedBy: "バイト１" }
];

const STAFF_LIST = ["マスター", "バイト１", "バイト２"];

const STORAGE_KEY = "cafe_zaiko_items";
const DATA_VERSION = 2; // バージョンが変わったらデフォルトデータをリセット
const VERSION_KEY = "cafe_zaiko_version";

// データ読み込み（なければデフォルトをセット）
function loadItems() {
    const ver = localStorage.getItem(VERSION_KEY);
    if (ver && parseInt(ver) >= DATA_VERSION) {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) return JSON.parse(stored);
    }
    // バージョンが古い or 初回 → デフォルトをセット
    localStorage.setItem(VERSION_KEY, DATA_VERSION);
    saveItems(DEFAULT_ITEMS);
    return JSON.parse(JSON.stringify(DEFAULT_ITEMS));
}

// データ保存
function saveItems(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

// 品目を名前で取得
function getItem(name) {
    const items = loadItems();
    return items.find(item => item.name === name);
}

// 品目を更新
function updateItem(name, updates) {
    const items = loadItems();
    const idx = items.findIndex(item => item.name === name);
    if (idx !== -1) {
        Object.assign(items[idx], updates);
        // アラート状態を再計算
        recalcAlert(items[idx]);
        saveItems(items);
    }
}

// アラート状態を在庫数と最低在庫から再計算
function recalcAlert(item) {
    if (item.qty <= 0) {
        item.dot = "red";
        item.badge = "要発注";
        item.badgeClass = "badge-expiry";
        item.alert = "要注意";
    } else if (item.qty <= item.minStock) {
        item.dot = "yellow";
        item.badge = "残少";
        item.badgeClass = "badge-low";
        item.alert = "要注意";
    } else {
        item.dot = "green";
        item.badge = "";
        item.badgeClass = "";
        item.alert = "";
    }
}

// サマリー計算
function calcSummary(items) {
    const total = items.length;
    const orderCount = items.filter(i => i.badge === "要発注").length;
    const lowCount = items.filter(i => i.alert === "要注意").length;
    return { total, orderCount, lowCount };
}
