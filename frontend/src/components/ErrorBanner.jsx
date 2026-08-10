// =============================================================================
// 이 파일의 책임: API 에러를 사용자에게 보여준다. api/http.js 인터셉터가
//   정규화한 Error 객체(code / message / status / requestId)를 그대로 받아
//   에러 코드별 안내 문구와 재시도 버튼을 함께 표시한다.
// 다른 파일과의 관계: pages/ListPage.jsx, pages/DetailPage.jsx 에서 사용한다.
//   에러 코드 값의 원본은 backend/app/core/error_codes.py 다.
// Spring 비교: @ControllerAdvice 가 만든 에러 응답을 화면에서 해석하는 쪽.
// =============================================================================

import './ErrorBanner.css'

// 서버 message 를 그대로 보여주되, 사용자가 다음에 무엇을 해야 하는지
// 알기 어려운 코드에만 보조 안내를 덧붙인다.
// 키는 backend/app/core/error_codes.py 의 ErrorCode 와 정확히 일치해야 한다.
const HINTS = {
  INVALID_FILE_TYPE: 'PDF, DOCX, HWPX, PNG, JPG 파일만 업로드할 수 있습니다.',
  FILE_TOO_LARGE: '파일 크기를 10MB 이하로 줄여 다시 시도해 주세요.',
  TOO_MANY_PAGES: '30페이지 이하로 나누어 업로드해 주세요.',
  CONTENT_TOO_LARGE: '문서 분량이 허용 범위를 넘었습니다. 일부만 잘라 업로드해 주세요.',
  EXTRACTION_FAILED: '문서에서 글자를 찾지 못했습니다. 스캔 품질을 확인해 주세요.',
  DOCUMENT_NOT_FOUND: '삭제되었거나 잘못된 주소일 수 있습니다. 목록으로 돌아가 주세요.',
  NOT_EXTRACTED_YET: '문서 상세 화면에서 분석을 먼저 실행해 주세요.',
  ANALYZER_NOT_FOUND: '요약 또는 분류 중 하나 이상을 선택해 주세요.',
  AI_PROVIDER_ERROR: 'AI 서비스 응답에 실패했습니다. 잠시 후 다시 시도해 주세요.',
  AI_TIMEOUT: '문서 분량이 많아 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.',
}


export default function ErrorBanner({ error, onRetry }) {
  if (!error) return null

  const hint = HINTS[error.code]

  return (
    <div className="error-banner" role="alert">
      <div className="error-banner__body">
        <p className="error-banner__message">
          {error.message || '요청 처리 중 오류가 발생했습니다.'}
        </p>
        {hint && <p className="error-banner__hint">{hint}</p>}

        {/* request_id 는 백엔드 로그와 대조할 때 쓴다. 디버깅·발표 시연에 유용. */}
        {(error.code || error.requestId) && (
          <p className="error-banner__meta">
            {error.code && <code>{error.code}</code>}
            {error.requestId && <code>{error.requestId}</code>}
          </p>
        )}
      </div>

      {onRetry && (
        <button type="button" className="error-banner__retry" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  )
}
