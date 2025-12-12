window.ExcelExport = {
  async exportTransactions() {
    try {
      // API에서 데이터 가져오기
      const response = await fetch('/api/receipts');
      if (!response.ok) {
        throw new Error('데이터를 불러올 수 없습니다.');
      }

      const receipts = await response.json();

      // 데이터가 없으면 경고
      if (!receipts || receipts.length === 0) {
        window.ToastHelper.warning('내보낼 데이터가 없습니다.');
        return;
      }

      // Excel 형식으로 변환
      const data = receipts.map(receipt => ({
        '날짜': dayjs(receipt.date || receipt.created_at).format('YYYY-MM-DD'),
        '카테고리': receipt.category || '',
        '상호명': receipt.store_name || receipt.merchant || '',
        '금액': receipt.total_amount || receipt.amount || 0
      }));

      // 워크시트 생성
      const ws = XLSX.utils.json_to_sheet(data);

      // 컬럼 너비 설정
      ws['!cols'] = [
        { wch: 12 },  // 날짜
        { wch: 10 },  // 카테고리
        { wch: 20 },  // 상호명
        { wch: 12 }   // 금액
      ];

      // 워크북 생성
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, '거래내역');

      // 파일 저장
      const filename = `거래내역_${dayjs().format('YYYY-MM-DD')}.xlsx`;
      XLSX.writeFile(wb, filename);

      // 성공 메시지
      window.ToastHelper.success('Excel 파일이 다운로드되었습니다!');

    } catch (error) {
      console.error('Excel export error:', error);
      window.ToastHelper.error('Excel 내보내기 중 오류가 발생했습니다.');
    }
  }
};
