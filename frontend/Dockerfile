FROM node:22-alpine

WORKDIR /app

# package.json, package-lock.json 복사
COPY package*.json ./

# 의존성 설치
RUN npm install

# 프로젝트 복사
COPY . .

# Vite 개발 서버 포트
EXPOSE 5173

# Docker 외부에서 접속 가능하도록 --host 옵션 사용
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]