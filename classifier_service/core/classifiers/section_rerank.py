"""
Section Rerank Module
Uses Cohere Rerank for fast section pre-classification
"""
from typing import Dict, Any, Optional, List
import cohere
from dotenv import load_dotenv
import json
import os
from pathlib import Path
import logfire

from ...api.v1.schemas import (
    SectionPreClassification,
    ProductAnalysis,
    RecommendedSection,
)

# Load environment variables
load_dotenv()

# Initialize Cohere client (lazy initialization to avoid import-time errors)
_cohere_client = None

def get_cohere_client():
    """Get or initialize Cohere client"""
    global _cohere_client
    if _cohere_client is None:
        api_key = os.getenv("CO_API_KEY")
        if not api_key:
            raise ValueError("CO_API_KEY environment variable is not set. Please set it to use Cohere reranking.")
        _cohere_client = cohere.ClientV2(api_key=api_key)
    return _cohere_client


def load_all_sections() -> List[Dict]:
    """Load all section knowledge bases"""
    sections_dir = Path(__file__).parent.parent.parent / "data" / "sections_knownledge_base"
    sections = []
    
    for json_file in sections_dir.glob("*.json"):
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                sections.extend(data)
            else:
                sections.append(data)
    
    return sections


def get_material_keywords(section_id: str) -> str:
    """
    Get material-specific keywords for each section to improve classification
    """
    material_guides = {
        "I": """
MATERIAL PRIORITY: Live animals and animal products (Động vật sống và các sản phẩm từ động vật).
Key Materials: Live animals (Động vật sống), Meat (Thịt), Fish (Cá), Dairy (Sữa), Eggs (Trứng), Honey (Mật ong), Animal products (Sản phẩm động vật)
Common Products: Live livestock (Gia súc sống), fresh/chilled/frozen meat and fish (Thịt cá tươi/đông lạnh), milk (Sữa), butter (Bơ), eggs (Trứng), natural honey (Mật ong tự nhiên)
Classification Rule: Live animals and unprocessed or minimally processed edible animal products (Động vật sống và sản phẩm động vật ăn được chưa chế biến hoặc sơ chế).
        """,
        "II": """
MATERIAL PRIORITY: Vegetable products (Các sản phẩm thực vật).
Key Materials: Live trees (Cây sống), plants (Thực vật), vegetables (Rau), fruits (Quả), coffee (Cà phê), tea (Chè), cereals (Ngũ cốc), seeds (Hạt), resins (Nhựa cây)
Common Products: Cut flowers (Hoa cắt), fresh/chilled/frozen vegetables and fruits (Rau quả tươi/đông lạnh), coffee beans (Hạt cà phê), tea leaves (Lá chè), rice (Gạo), wheat (Lúa mì), flour (Bột), oil seeds (Hạt có dầu)
Classification Rule: Plants and unprocessed or minimally processed vegetable products (Thực vật và sản phẩm thực vật chưa chế biến hoặc sơ chế).
        """,
        "III": """
MATERIAL PRIORITY: Animal or vegetable fats and oils (Chất béo và dầu động vật hoặc thực vật).
Key Materials: Animal fats (Mỡ động vật), vegetable oils (Dầu thực vật), waxes (Sáp)
Common Products: Lard (Mỡ lợn), soybean oil (Dầu đậu nành), olive oil (Dầu ô liu), palm oil (Dầu cọ), margarine (Bơ thực vật), waxes (Sáp)
Classification Rule: Fats, oils, and their cleavage products; prepared edible fats; animal or vegetable waxes (Chất béo, dầu và các sản phẩm tách từ chúng; chất béo ăn được đã chế biến; sáp động vật hoặc thực vật).
        """,
        "IV": """
MATERIAL PRIORITY: Prepared foodstuffs; beverages, spirits, and vinegar; tobacco (Thực phẩm chế biến; đồ uống, rượu và giấm; thuốc lá).
Key Materials: Processed meat/fish/vegetables (Thịt/cá/rau chế biến), sugar (Đường), cocoa (Ca cao), cereal preparations (Chế phẩm ngũ cốc), beverages (Đồ uống), alcohol (Rượu), tobacco (Thuốc lá)
Common Products: Sausages (Xúc xích), canned food (Đồ hộp), confectionery (Bánh kẹo), chocolate (Sô cô la), bread (Bánh mì), pastry (Bánh ngọt), juices (Nước ép), beer (Bia), wine (Rượu vang), cigarettes (Thuốc lá điếu)
Classification Rule: Processed food and beverages not covered in Sections I-III (Thực phẩm và đồ uống đã chế biến không thuộc Phần I-III).
        """,
        "V": """
MATERIAL PRIORITY: Mineral products (Khoáng sản).
Key Materials: Salt (Muối), sulphur (Lưu huỳnh), earths (Đất), stone (Đá), ores (Quặng), mineral fuels (Nhiên liệu khoáng), mineral oils (Dầu khoáng)
Common Products: Salt (Muối), cement (Xi măng), ores (Quặng), coal (Than đá), petroleum oils (Dầu mỏ), natural gas (Khí tự nhiên), electricity (Điện)
Classification Rule: Raw mineral products and fuels (Khoáng sản thô và nhiên liệu).
        """,
        "VI": """
MATERIAL PRIORITY: Products of the chemical or allied industries (Sản phẩm của ngành công nghiệp hóa chất hoặc các ngành liên quan).
Key Materials: Inorganic/organic chemicals (Hóa chất vô cơ/hữu cơ), pharmaceuticals (Dược phẩm), fertilizers (Phân bón), paints (Sơn), cosmetics (Mỹ phẩm), soaps (Xà phòng), glues (Keo dán), explosives (Chất nổ)
Common Products: Acids (Axit), medicaments (Thuốc chữa bệnh), vaccines (Vắc-xin), fertilizers (Phân bón), inks (Mực), perfumes (Nước hoa), soaps (Xà phòng), washing preparations (Chất tẩy rửa), adhesives (Keo dán)
Classification Rule: Products characterized by their chemical composition or use in chemical industries (Sản phẩm đặc trưng bởi thành phần hóa học hoặc dùng trong công nghiệp hóa chất).
        """,
        "VII": """
MATERIAL PRIORITY: This section is for articles made OF plastic or rubber as their PRIMARY material (Sản phẩm làm từ Plastic hoặc Cao su).
Key Materials: Plastic (all types: PET, PVC, PE, PP, PS, ABS), Rubber (natural, synthetic), Polymer, Elastomer (Plastic các loại, Cao su tự nhiên/tổng hợp)
Common Products: Plastic bottles (Chai nhựa), bags (Túi), containers (Hộp chứa), sheets (Tấm), tubes (Ống), films (Màng); Rubber tires (Lốp cao su), tubes (Săm), seals (Phớt), gaskets (Gioăng), hoses (Vòi)
Classification Rule: If the MAIN material is plastic or rubber, classify here FIRST (unless it's a specific vehicle/aircraft/vessel part) (Nếu vật liệu chính là plastic hoặc cao su, phân loại vào đây TRƯỚC, trừ khi là bộ phận chuyên dùng cho xe/máy bay/tàu thuyền).
Examples: Plastic water bottles, plastic shopping bags, rubber gloves, plastic toys, rubber seals, plastic packaging
        """,
        "VIII": """
MATERIAL PRIORITY: Raw hides and skins, leather, furskins, and articles thereof (Da sống, da thuộc, da lông và các sản phẩm từ chúng).
Key Materials: Leather (Da thuộc), furskin (Da lông), animal gut (Ruột động vật)
Common Products: Saddlery (Yên cương), travel goods (Hàng du lịch), handbags (Túi xách), wallets (Ví), animal gut articles (Sản phẩm từ ruột động vật)
Classification Rule: Articles made of leather, furskin, or animal gut; travel goods (Sản phẩm làm từ da, da lông hoặc ruột động vật; hàng du lịch).
        """,
        "IX": """
MATERIAL PRIORITY: Wood and articles of wood; cork; manufactures of straw/plaiting materials (Gỗ và các mặt hàng bằng gỗ; lie; sản phẩm từ rơm rạ/vật liệu tết bện).
Key Materials: Wood (Gỗ), charcoal (Than củi), cork (Lie), straw (Rơm), bamboo (Tre), rattan (Mây)
Common Products: Lumber (Gỗ xẻ), plywood (Gỗ dán), wooden boxes (Hộp gỗ), cork stoppers (Nút bần), basketware (Hàng mây tre đan)
Classification Rule: Articles made of wood, cork, or plaiting materials (Sản phẩm làm từ gỗ, lie, hoặc vật liệu tết bện).
        """,
        "X": """
MATERIAL PRIORITY: Pulp of wood, paper and paperboard (Bột giấy, giấy và bìa).
Key Materials: Wood pulp (Bột gỗ), paper (Giấy), paperboard (Bìa)
Common Products: Paper rolls (Cuộn giấy), cardboard boxes (Hộp bìa các tông), notebooks (Vở), printed books (Sách in), newspapers (Báo)
Classification Rule: Pulp, paper, paperboard, and printed matter (Bột giấy, giấy, bìa và ấn phẩm in).
        """,
        "XI": """
MATERIAL PRIORITY: Textiles and textile articles (Dệt may và các sản phẩm dệt).
Key Materials: Silk (Tơ tằm), wool (Len), cotton (Bông), man-made filaments/fibres (Xơ/sợi nhân tạo)
Common Products: Yarns (Sợi), woven/knitted fabrics (Vải dệt thoi/dệt kim), carpets (Thảm), apparel (Quần áo), clothing accessories (Phụ kiện may mặc), blankets (Chăn), bed linen (Ga trải giường)
Classification Rule: Textiles, clothing, and made-up textile articles (Hàng dệt, quần áo và các sản phẩm dệt đã hoàn thiện).
        """,
        "XII": """
MATERIAL PRIORITY: Footwear, headgear, umbrellas, sun umbrellas, walking-sticks, whips, riding-crops, and parts thereof; prepared feathers and articles made therewith; artificial flowers; articles of human hair (Giày dép, mũ, ô dù, gậy, roi; lông vũ chế biến; hoa nhân tạo; sản phẩm từ tóc người).
Key Materials: Various materials used for footwear/headgear (leather, rubber, textile), feathers (Lông vũ), artificial flowers (Hoa nhân tạo), human hair (Tóc người)
Common Products: Shoes (Giày), boots (Ủng), hats (Mũ), umbrellas (Ô dù), wigs (Tóc giả), artificial flowers (Hoa nhân tạo)
Classification Rule: Footwear, headgear, and specific accessory articles (Giày dép, mũ và các phụ kiện cụ thể).
        """,
        "XIII": """
MATERIAL PRIORITY: Articles of stone, plaster, cement, asbestos, mica or similar materials; ceramic products; glass and glassware (Sản phẩm bằng đá, thạch cao, xi măng, amiăng, mica; gốm sứ; thủy tinh).
Key Materials: Stone (Đá), plaster (Thạch cao), cement (Xi măng), asbestos (Amiăng), ceramic (Gốm sứ), glass (Thủy tinh)
Common Products: Concrete blocks (Gạch bê tông), ceramic tiles (Gạch men), tableware (Bộ đồ ăn), glass bottles (Chai thủy tinh), fiberglass (Sợi thủy tinh), laboratory glassware (Dụng cụ thí nghiệm thủy tinh)
Classification Rule: Articles made of stone, ceramic, or glass (Sản phẩm làm từ đá, gốm sứ hoặc thủy tinh).
        """,
        "XIV": """
MATERIAL PRIORITY: Natural or cultured pearls, precious or semi-precious stones, precious metals, metals clad with precious metal, and articles thereof; imitation jewellery; coin (Ngọc trai, đá quý, kim loại quý và các sản phẩm từ chúng; đồ trang sức giả; tiền kim loại).
Key Materials: Pearls (Ngọc trai), diamonds (Kim cương), gemstones (Đá quý), gold (Vàng), silver (Bạc), platinum (Bạch kim)
Common Products: Jewelry (Trang sức), goldsmiths' wares (Nữ trang), coins (Tiền kim loại)
Classification Rule: Articles made of precious metals/stones or imitation jewelry (Sản phẩm làm từ kim loại/đá quý hoặc trang sức giả).
        """,
        "XV": """
MATERIAL PRIORITY: Base metals (iron, steel, copper, aluminum, lead, zinc, tin, etc.) and articles thereof (Kim loại cơ bản và các sản phẩm từ chúng).
Key Materials: Iron (Sắt), Steel (Thép), Copper (Đồng), Aluminum (Nhôm), Nickel (Niken), Lead (Chì), Zinc (Kẽm), Tin (Thiếc), metal alloys (Hợp kim)
Common Products: Metal sheets (Tấm kim loại), tubes (Ống), nails (Đinh), screws (Ốc vít), tools (Dụng cụ), containers (Thùng chứa), structures (Kết cấu)
Classification Rule: Articles primarily made of base metals (not precious metals) (Sản phẩm chủ yếu làm từ kim loại cơ bản, không phải kim loại quý).
        """,
        "XVI": """
APPLICATION PRIORITY: Machinery, mechanical appliances, and electrical equipment (Máy móc, thiết bị cơ khí và thiết bị điện).
Focus: FUNCTIONAL machinery and equipment, not simple articles (Máy móc và thiết bị CHỨC NĂNG, không phải vật dụng đơn giản)
Key Products: Motors (Động cơ), engines (Máy), pumps (Bơm), machines (Máy móc), electrical equipment (Thiết bị điện), machinery parts (Bộ phận máy)
Classification Rule: For industrial/commercial machinery and equipment with mechanical or electrical function (Dành cho máy móc, thiết bị công nghiệp/thương mại có chức năng cơ khí hoặc điện).
        """,
        "XVII": """
APPLICATION PRIORITY: Complete vehicles and their specialized parts (Xe cộ hoàn chỉnh và các bộ phận chuyên dùng).
Focus: Vehicles themselves or parts SPECIFICALLY designed for vehicles (Xe cộ hoặc các bộ phận được thiết kế ĐẶC BIỆT cho xe)
Key Products: Cars (Ô tô), motorcycles (Xe máy), aircraft (Máy bay), ships (Tàu thuyền), vehicle chassis (Khung gầm xe), vehicle engines (Động cơ xe), specific vehicle parts (Bộ phận xe chuyên dùng)
Classification Rule: For vehicles OR parts that are INTEGRAL and SPECIFIC to vehicle function (Dành cho xe cộ HOẶC các bộ phận CẤU THÀNH và CỤ THỂ cho chức năng của xe).
Note: A plastic/rubber part used in a vehicle but not specific to vehicles goes to Section VII (Lưu ý: Bộ phận bằng nhựa/cao su dùng trên xe nhưng không đặc thù cho xe thì thuộc Phần VII).
        """,
        "XVIII": """
APPLICATION PRIORITY: Precision instruments and apparatus (Dụng cụ và thiết bị chính xác).
Key Products: Optical (Quang học), photographic (Nhiếp ảnh), measuring (Đo lường), medical instruments (Dụng cụ y tế), watches (Đồng hồ đeo tay), clocks (Đồng hồ treo tường)
Classification Rule: For precision instruments requiring specialized function (Dành cho các dụng cụ chính xác đòi hỏi chức năng chuyên biệt).
        """,
        "XIX": """
MATERIAL PRIORITY: Arms and ammunition; parts and accessories thereof (Vũ khí và đạn dược; các bộ phận và phụ kiện).
Key Materials: Metals (Kim loại), explosives (Chất nổ), plastics (Nhựa)
Common Products: Military weapons (Vũ khí quân dụng), sporting guns (Súng thể thao), ammunition (Đạn), swords (Kiếm)
Classification Rule: Arms and ammunition (Vũ khí và đạn dược).
        """,
        "XX": """
CATCH-ALL: Miscellaneous manufactured articles not elsewhere specified (Các mặt hàng đã qua chế biến khác chưa được chi tiết ở nơi khác).
Key Products: Furniture (Đồ nội thất), toys (Đồ chơi), games (Trò chơi), sports equipment (Dụng cụ thể thao), misc. manufactured goods (Hàng hóa chế biến khác)
Classification Rule: When articles don't fit other sections (Khi sản phẩm không phù hợp với các Phần khác).
        """,
        "XXI": """
MATERIAL PRIORITY: Works of art, collectors' pieces and antiques (Tác phẩm nghệ thuật, đồ sưu tầm và đồ cổ).
Key Materials: Any material (canvas, stone, metal) (Mọi chất liệu: vải, đá, kim loại...)
Common Products: Paintings (Tranh), sculptures (Tượng), stamp collections (Bộ sưu tập tem), antiques (>100 years) (Đồ cổ trên 100 năm)
Classification Rule: Works of art and antiques (Tác phẩm nghệ thuật và đồ cổ).
        """
    }
    return material_guides.get(section_id, "")


def prepare_documents_for_rerank(sections: List[Dict]) -> tuple[List[str], List[Dict]]:
    """
    Prepare section data for reranking with comprehensive information
    """
    documents = []
    metadata = []
    
    for section in sections:
        # Basic information
        section_id = section.get('section_id', 'N/A')
        title_en = section.get('section_title', {}).get('en', 'N/A')
        title_vi = section.get('section_title', {}).get('vi', 'N/A')
        summary_en = section.get('summary', {}).get('en', '')
        summary_vi = section.get('summary', {}).get('vi', '')
        
        # Build comprehensive document text
        doc_parts = [
            f"Section {section_id}: {title_en}",
            f"Vietnamese Title: {title_vi}",
            ""
        ]
        
        # Add material/application guidance
        material_guide = get_material_keywords(section_id)
        if material_guide:
            doc_parts.append("=== CLASSIFICATION GUIDANCE ===")
            doc_parts.append(material_guide)
            doc_parts.append("")
        
        doc_parts.extend([
            "=== DETAILED INFORMATION ===",
            "SUMMARY:",
            summary_en,
            summary_vi,
            ""
        ])
        
        # Add notes
        notes = section.get('notes', [])
        if notes:
            doc_parts.append("CLASSIFICATION NOTES:")
            for note in notes:
                content = note.get('content', {})
                note_en = content.get('en', '')
                note_vi = content.get('vi', '')
                if note_en:
                    doc_parts.append(f"- {note_en}")
                if note_vi:
                    doc_parts.append(f"- {note_vi}")
            doc_parts.append("")
        
        # Add general information
        general = section.get('general', [])
        if general:
            doc_parts.append("GENERAL INFORMATION:")
            for gen in general:
                content = gen.get('content', {})
                gen_en = content.get('en', '')
                gen_vi = content.get('vi', '')
                if gen_en:
                    doc_parts.append(f"- {gen_en}")
                if gen_vi:
                    doc_parts.append(f"- {gen_vi}")
            doc_parts.append("")
        
        # Add chapter information
        chapters = section.get('chapters', [])
        if chapters:
            doc_parts.append("CHAPTERS IN THIS SECTION:")
            for chapter in chapters:
                chapter_id = chapter.get('chapter_id', 'N/A')
                chapter_title_en = chapter.get('chapter_title', {}).get('en', 'N/A')
                chapter_title_vi = chapter.get('chapter_title', {}).get('vi', 'N/A')
                doc_parts.append(f"Chapter {chapter_id}: {chapter_title_en} / {chapter_title_vi}")
            doc_parts.append("")
        
        # Combine all parts
        doc_text = "\n".join(doc_parts)
        
        documents.append(doc_text)
        metadata.append({
            'section_id': section_id,
            'title_en': title_en,
            'title_vi': title_vi
        })
    
    return documents, metadata


def format_query_for_rerank(query_data: Dict[str, Any]) -> str:
    """
    Format query data for rerank
    """
    parts = []
    
    if query_data.get('product_name'):
        parts.append(f"Tên sản phẩm: {query_data['product_name']}")
    
    if query_data.get('science_name'):
        parts.append(f"Tên khoa học: {query_data['science_name']}")

    if query_data.get('product_description'):
        parts.append(f"Mô tả sản phẩm: {query_data['product_description']}")
    
    if query_data.get('function'):
        parts.append(f"Chức năng: {query_data['function']}")
    
    if query_data.get('structure'):
        parts.append(f"Cấu trúc: {query_data['structure']}")
    
    if query_data.get('material'):
        parts.append(f"Vật liệu: {query_data['material']}")
    
    if query_data.get('specifications'):
        parts.append(f"Thông số kỹ thuật: {query_data['specifications']}")
    
    return "\n".join(parts)


def _build_product_dna(query_data: Dict[str, Any]) -> str:
    parts: List[str] = []

    def add_value(label: str, value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text:
            parts.append(f"{label}: {text}")

    add_value("Tên", query_data.get("product_name"))
    add_value("Chất liệu", query_data.get("material"))
    add_value("Công dụng", query_data.get("function"))
    add_value("Tình trạng", query_data.get("structure") or query_data.get("description"))

    return "; ".join(parts)


# Cache for sections and documents
_SECTIONS_CACHE = None
_DOCUMENTS_CACHE = None
_METADATA_CACHE = None


def _get_cached_data():
    """Get cached section data or load it"""
    global _SECTIONS_CACHE, _DOCUMENTS_CACHE, _METADATA_CACHE
    
    if _SECTIONS_CACHE is None:
        _SECTIONS_CACHE = load_all_sections()
        _DOCUMENTS_CACHE, _METADATA_CACHE = prepare_documents_for_rerank(_SECTIONS_CACHE)
    
    return _DOCUMENTS_CACHE, _METADATA_CACHE


def pre_classify_section_with_rerank(
    query_data: Dict[str, Any], 
    top_n: int = 3,
    min_score: float = 0.1
) -> Optional[SectionPreClassification]:
    """
    Pre-classify sections using Cohere Rerank
    
    Args:
        query_data: Dictionary with product information
        top_n: Number of top sections to return (default: 3)
        min_score: Minimum relevance score threshold (default: 0.1)
    
    Returns:
        SectionPreClassification with product analysis and recommended sections
        None if no sections meet the minimum score threshold
    """
    with logfire.span(
        "Pre-Classify Section (Rerank)",
        classification_level="section_pre_rerank",
        product_name=query_data.get('product_name', 'N/A')
    ):
        try:
            # Format query
            query_text = format_query_for_rerank(query_data)
            
            if not query_text.strip():
                logfire.error("Query data is empty")
                return None
            
            # Get cached documents and metadata
            documents, metadata = _get_cached_data()
            
            # Perform rerank
            logfire.info(f"Reranking with query length: {len(query_text)} characters")
            co = get_cohere_client()
            response = co.rerank(
                model="rerank-v3.5",
                query=query_text,
                documents=documents,
                top_n=min(top_n, len(documents)),
            )
            
            # Extract results
            candidate_ids = []
            scores = []
            
            for result in response.results:
                idx = result.index
                score = result.relevance_score
                
                # Apply minimum score filter
                if score >= min_score:
                    section_id = metadata[idx]['section_id']
                    candidate_ids.append(section_id)
                    scores.append(score)
            
            if not candidate_ids:
                logfire.warning("No sections met minimum score threshold")
                return None
            
            logfire.info(
                "Section pre-classified with rerank",
                recommended_section_ids=candidate_ids,
                scores=scores,
                top1_score=scores[0] if scores else 0,
                score_gap=scores[0] - scores[1] if len(scores) > 1 else 0
            )

            recommended_sections = []
            for section_id, score in zip(candidate_ids, scores):
                scaled_score = max(1.0, min(10.0, score * 10))
                recommended_sections.append(
                    RecommendedSection(
                        section_id=section_id,
                        section_title_snippet="",
                        confidence_score=scaled_score,
                        gir_application="Rerank relevance score",
                        rationale=f"Rerank score: {score:.4f}",
                    )
                )

            return SectionPreClassification(
                product_analysis=ProductAnalysis(product_dna=_build_product_dna(query_data)),
                recommended_sections=recommended_sections,
            )
            
        except Exception as e:
            logfire.error(f"Error during rerank section pre-classification: {e}")
            return None
