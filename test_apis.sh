#!/bin/bash

echo "================================================================================"
echo "🧪 HS Code Services API Tests"
echo "================================================================================"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "\n${BLUE}1️⃣  Testing Classifier API${NC}"
echo "Endpoint: POST http://localhost:8080/api/v1/classify/"
echo "Note: This may take 1-2 minutes due to LLM processing..."
echo "--------------------------------------------------------------------------------"

curl -X POST http://localhost:8080/api/v1/classify/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --max-time 180 \
  -d '{
    "product_name": "Máy chiếu phim gia đình (Home Cinema Projector)",
    "science_name": "DIGITAL LIGHT PROCESSING (DLP) PROJECTOR, PORTABLE, WITH BUILT-IN SPEAKER AND WI-FI CONNECTIVITY",
    "product_description": "Máy chiếu sử dụng công nghệ DLP. Tích hợp loa ngoài công suất 10W để phát âm thanh. Tích hợp module Wi-Fi cho phép kết nối mạng không dây và truyền nội dung (chức năng Smart TV). Được đóng gói để bán lẻ như một bộ thiết bị giải trí duy nhất.",
    "function": "Chiếu hình ảnh và video (chức năng cốt lõi); Phát âm thanh và nhận/truyền dữ liệu qua Wi-Fi (chức năng bổ trợ).",
    "structure": "Cấu trúc hỗn hợp: Bộ phận chiếu hình ảnh + Loa/Mạch khuếch đại + Module Wi-Fi/Board điều khiển chính.",
    "specifications": "Độ phân giải: 1920x1080; Công suất loa: 10W; Kết nối Wi-Fi 802.11ac."
  }' | jq . > /tmp/classifier_result.json

echo -e "\n${GREEN}✅ Result saved to: /tmp/classifier_result.json${NC}"
cat /tmp/classifier_result.json

echo -e "\n\n${BLUE}2️⃣  Testing RAG API${NC}"
echo "Endpoint: POST http://localhost:8080/api/v1/search/hscode"
echo "Note: This may take 20-30 seconds due to vector search + LLM processing..."
echo "--------------------------------------------------------------------------------"

curl -X POST http://localhost:8080/api/v1/search/hscode \
  -H "Accept: application/json" \
  --max-time 180 \
  -F "product_name=Máy chiếu phim gia đình (Home Cinema Projector)" \
  -F "science_name=DIGITAL LIGHT PROCESSING (DLP) PROJECTOR, PORTABLE, WITH BUILT-IN SPEAKER AND WI-FI CONNECTIVITY" \
  -F "product_description=Máy chiếu sử dụng công nghệ DLP. Tích hợp loa ngoài công suất 10W để phát âm thanh. Tích hợp module Wi-Fi cho phép kết nối mạng không dây và truyền nội dung (chức năng Smart TV). Được đóng gói để bán lẻ như một bộ thiết bị giải trí duy nhất." \
  -F "function=Chiếu hình ảnh và video (chức năng cốt lõi); Phát âm thanh và nhận/truyền dữ liệu qua Wi-Fi (chức năng bổ trợ)." \
  -F "structure=Cấu trúc hỗn hợp: Bộ phận chiếu hình ảnh + Loa/Mạch khuếch đại + Module Wi-Fi/Board điều khiển chính." \
  -F "specifications=Độ phân giải: 1920x1080; Công suất loa: 10W; Kết nối Wi-Fi 802.11ac." \
  | jq . > /tmp/rag_result.json

echo -e "\n${GREEN}✅ Result saved to: /tmp/rag_result.json${NC}"
cat /tmp/rag_result.json

echo -e "\n\n================================================================================"
echo -e "${GREEN}✅ All tests complete!${NC}"
echo "================================================================================"
echo "Results saved to:"
echo "  - /tmp/classifier_result.json"
echo "  - /tmp/rag_result.json"
echo "================================================================================"
