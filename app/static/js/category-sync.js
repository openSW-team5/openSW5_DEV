// 카테고리 동기화 관리 모듈
const CategorySync = {
    STORAGE_KEY: 'expense_categories',
    CHANGED_EVENT: 'expense_categories:changed',

    DEFAULT_CATEGORIES: [
        { name: '식비', spent: 250000, budget: 500000, icon: 'food.svg' },
        { name: '교통', spent: 80000, budget: 150000, icon: 'Transportation.svg' },
        { name: '쇼핑', spent: 120000, budget: 200000, icon: 'shop.svg' },
        { name: '여가', spent: 50000, budget: 100000, icon: 'Leisure.svg' },
        { name: '의료', spent: 30000, budget: 100000, icon: 'Healthcare.svg' },
        { name: '주거', spent: 400000, budget: 500000, icon: 'Housing.svg' },
        { name: '통신', spent: 60000, budget: 80000, icon: 'Communications.svg' },
        { name: '기타', spent: 10000, budget: 50000, icon: 'Other.svg' },
    ],

    getCategories() {
        try {
            const stored = localStorage.getItem(this.STORAGE_KEY);
            if (stored) return JSON.parse(stored);
        } catch (error) {
            console.error('Failed to load categories from localStorage:', error);
        }

        // 없으면 기본값 저장
        this.saveCategories(this.DEFAULT_CATEGORIES);
        return this.DEFAULT_CATEGORIES;
    },

    // ✅ 같은 탭 업데이트를 위해 커스텀 이벤트도 쏨
    saveCategories(categories) {
        try {
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(categories));

            // 같은 탭(현재 탭) 즉시 반영용 이벤트
            window.dispatchEvent(
                new CustomEvent(this.CHANGED_EVENT, {
                    detail: { categories },
                })
            );

            // 다른 탭은 브라우저가 자동으로 storage 이벤트 발생시킴
            return true;
        } catch (error) {
            console.error('Failed to save categories to localStorage:', error);
            return false;
        }
    },

    addCategory(name, icon = 'folder-simple-duotone.svg', budget = 0) {
        const categories = this.getCategories();
        categories.push({ name, spent: 0, budget, icon });
        return this.saveCategories(categories);
    },

    deleteCategory(index) {
        const categories = this.getCategories();
        if (index >= 0 && index < categories.length) {
            categories.splice(index, 1);
            return this.saveCategories(categories);
        }
        return false;
    },

    renameCategory(index, newName) {
        const categories = this.getCategories();
        if (index >= 0 && index < categories.length) {
            categories[index].name = newName;
            return this.saveCategories(categories);
        }
        return false;
    },

    updateBudget(index, budget) {
        const categories = this.getCategories();
        if (index >= 0 && index < categories.length) {
            categories[index].budget = budget;
            return this.saveCategories(categories);
        }
        return false;
    },

    updateSpent(index, spent) {
        const categories = this.getCategories();
        if (index >= 0 && index < categories.length) {
            categories[index].spent = spent;
            return this.saveCategories(categories);
        }
        return false;
    },

    // ✅ “같은 탭” + “다른 탭” 둘 다 잡는 리스너
    onChange(callback) {
        // 같은 탭 (CustomEvent)
        window.addEventListener(this.CHANGED_EVENT, (e) => {
            callback(e.detail?.categories ?? this.getCategories());
        });

        // 다른 탭 (StorageEvent) - 같은 탭에서는 원래 안 뜸
        window.addEventListener('storage', (e) => {
            if (e.key === this.STORAGE_KEY) {
                callback(this.getCategories());
            }
        });
    },

    resetCategories() {
        this.saveCategories(this.DEFAULT_CATEGORIES);
        return this.DEFAULT_CATEGORIES;
    },
};

window.CategorySync = CategorySync;
