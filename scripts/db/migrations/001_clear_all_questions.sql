-- Migration 001: 清空题库（部署时同步清理线上旧题目，再导入 pay/ 付费真题）
-- 适用场景：从免费网页/OCR 源切换为爱真题付费版全量重建

TRUNCATE questions, exam_papers, subjects RESTART IDENTITY CASCADE;
