// =============================================================================
// 이 파일의 책임: 서버가 준 blob 을 브라우저 다운로드로 연결하고, 응답 헤더에서
//   파일 이름을 꺼낸다.
// 다른 파일과의 관계: api/document.js(원본·요약 다운로드)와
//   api/deliverable.js(산출물 다운로드)가 함께 쓴다.
// Spring 비교: 해당 없음 — 브라우저 쪽 처리다. 서버에서 파일 이름을 정하는 쪽은
//   FileResponse(filename=...) 이고, 여기서는 그 헤더를 읽기만 한다.
//
// 왜 따로 뺐는가
//   전에는 api/document.js 안에만 있었다. 산출물 다운로드가 생기면서 같은 코드가
//   필요해졌는데, 복사하면 한쪽만 고쳐서 **한글 파일명이 한 화면에서만 깨지는**
//   일이 생긴다. 에러가 나지 않아 알아채기 어렵다.
// =============================================================================

/** `Content-Disposition` 에서 파일 이름을 꺼낸다.
 *
 * 예: `attachment; filename="summary.txt"; filename*=UTF-8''%ED%95%9C...`
 *
 * `filename*=UTF-8''` 를 먼저 본다 — 한글 이름이 그쪽에 담긴다. 서버가
 * FileResponse 에 한글 filename 을 주면 RFC 5987 로 그렇게 인코딩된다.
 */
export function parseFilename(disposition, fallback) {
  if (!disposition) return fallback

  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      // 디코딩 실패 시 아래 filename= 으로 넘어간다
    }
  }

  const asciiMatch = disposition.match(/filename="?([^";]+)"?/i)
  return asciiMatch ? asciiMatch[1] : fallback
}

/** blob 을 사용자 다운로드로 연결한다. a 태그를 임시로 만들어 클릭한다.
 *
 * `createObjectURL` 로 만든 URL 은 **반드시 되돌려준다**(revoke). 그러지 않으면
 * 파일을 받을 때마다 메모리에 blob 이 남는다.
 */
export function triggerBrowserDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}
