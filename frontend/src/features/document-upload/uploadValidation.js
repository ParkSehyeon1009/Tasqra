export const MAX_UPLOAD_FILE_SIZE = 10 * 1024 * 1024

const ALLOWED_EXTENSIONS = new Set(['pdf', 'docx', 'hwpx', 'png', 'jpg', 'jpeg'])

export function getUploadFileKey(file) {
  return [file.name.toLowerCase(), file.size, file.lastModified].join(':')
}

export function isImageUpload(file) {
  return /\.(png|jpe?g)$/i.test(file?.name ?? '')
}

export function validateUploadFiles(files) {
  const seen = new Set()
  return Array.from(files ?? []).map((file, index) => {
    const fileKey = getUploadFileKey(file)
    let error = null
    const extension = file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : ''

    if (seen.has(fileKey)) error = '같은 파일이 선택 목록에 중복되어 있습니다.'
    else if (!ALLOWED_EXTENSIONS.has(extension)) error = '지원하지 않는 파일 형식입니다.'
    else if (file.size === 0) error = '빈 파일은 업로드할 수 없습니다.'
    else if (file.size > MAX_UPLOAD_FILE_SIZE) error = '파일은 최대 10MB까지 업로드할 수 있습니다.'

    seen.add(fileKey)
    return { file, key: `${fileKey}:${index}`, index, error }
  })
}
