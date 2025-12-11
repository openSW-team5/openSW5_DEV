// 카테고리 동기화 관리 모듈
const CategorySync = {
  STORAGE_KEY: 'expense_categories',

  // 기본 카테고리 데이터
  DEFAULT_CATEGORIES: [
    { name: '식비', spent: 250000, budget: 500000, icon: 'food.svg' },
    { name: '교통', spent: 80000, budget: 150000, icon: 'Transportation.svg' },
    { name: '쇼핑', spent: 120000, budget: 200000, icon: 'shop.svg' },
    { name: '여가', spent: 50000, budget: 100000, icon: 'Leisure.svg' },
    { name: '의료', spent: 30000, budget: 100000, icon: 'Healthcare.svg' },
    { name: '주거', spent: 400000, budget: 500000, icon: 'Housing.svg' },
    { name: '통신', spent: 60000, budget: 80000, icon: 'Communications.svg' },
    { name: '기타', spent: 10000, budget: 50000, icon: 'Other.svg' }
  ],

  // localStorage에서 카테고리 가져오기
  getCategories() {
    try {
      const stored = localStorage.getItem(this.STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (error) {
      console.error('Failed to load categories from localStorage:', error);
    }
    // localStorage에 없으면 기본값 저장하고 반환
    this.saveCategories(this.DEFAULT_CATEGORIES);
    return this.DEFAULT_CATEGORIES;
  },

  // localStorage에 카테고리 저장
  saveCategories(categories) {
    try {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(categories));
      // 다른 탭/창에 변경사항 알림
      window.dispatchEvent(new Event('storage'));
      return true;
    } catch (error) {
      console.error('Failed to save categories to localStorage:', error);
      return false;
    }
  },

  // 카테고리 추가
  addCategory(name, icon = 'folder-simple-duotone.svg', budget = 0) {
    const categories = this.getCategories();
    categories.push({
      name: name,
      spent: 0,
      budget: budget,
      icon: icon
    });
    return this.saveCategories(categories);
  },

  // 카테고리 삭제
  deleteCategory(index) {
    const categories = this.getCategories();
    if (index >= 0 && index < categories.length) {
      categories.splice(index, 1);
      return this.saveCategories(categories);
    }
    return false;
  },

  // 카테고리 이름 변경
  renameCategory(index, newName) {
    const categories = this.getCategories();
    if (index >= 0 && index < categories.length) {
      categories[index].name = newName;
      return this.saveCategories(categories);
    }
    return false;
  },

  // 카테고리 예산 업데이트
  updateBudget(index, budget) {
    const categories = this.getCategories();
    if (index >= 0 && index < categories.length) {
      categories[index].budget = budget;
      return this.saveCategories(categories);
    }
    return false;
  },

  // 카테고리 지출액 업데이트
  updateSpent(index, spent) {
    const categories = this.getCategories();
    if (index >= 0 && index < categories.length) {
      categories[index].spent = spent;
      return this.saveCategories(categories);
    }
    return false;
  },

  // storage 이벤트 리스너 (다른 탭에서 변경시 동기화)
  onStorageChange(callback) {
    window.addEventListener('storage', (e) => {
      if (e.key === this.STORAGE_KEY || e.key === null) {
        callback(this.getCategories());
      }
    });
  },

  // 모든 카테고리 초기화
  resetCategories() {
    this.saveCategories(this.DEFAULT_CATEGORIES);
    return this.DEFAULT_CATEGORIES;
  }
};

// 전역으로 사용 가능하도록 설정
window.CategorySync = CategorySync;
