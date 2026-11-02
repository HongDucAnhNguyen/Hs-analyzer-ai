import os
import json
import glob
import urllib.parse
import tempfile
import shutil
from pathlib import Path
from llama_cloud_services import LlamaParse
from dotenv import load_dotenv
import fitz  # PyMuPDF
from PIL import Image

load_dotenv()

def pdf_to_images(pdf_path, temp_dir, dpi=200, image_format="png"):
    """
    Convert PDF pages to individual images
    
    Args:
        pdf_path (str): Path to the PDF file
        temp_dir (str): Temporary directory for images
        dpi (int): DPI for image quality (default: 200)
        image_format (str): Output image format - 'png' or 'jpeg' (default: 'png')
    
    Returns:
        list: List of generated image file paths
    """
    try:
        pdf_document = fitz.open(pdf_path)
        image_files = []
        
        pdf_name = Path(pdf_path).stem
        total_pages = len(pdf_document)
        
        print(f"Converting {pdf_name}.pdf ({total_pages} pages) to images...")
        
        for page_num in range(total_pages):
            # Get page
            page = pdf_document[page_num]
            
            # Set zoom factor based on DPI (72 is default PDF DPI)
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            
            # Render page to image
            pix = page.get_pixmap(matrix=mat)
            
            # Generate output filename
            if image_format.lower() == 'jpeg':
                output_filename = f"{pdf_name}_page_{page_num + 1:03d}.jpg"
            else:
                output_filename = f"{pdf_name}_page_{page_num + 1:03d}.png"
            
            output_path = os.path.join(temp_dir, output_filename)
            
            # Save image
            if image_format.lower() == 'jpeg':
                # Convert to RGB for JPEG (PyMuPDF returns RGBA)
                img = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)
                img = img.convert("RGB")
                img.save(output_path, "JPEG", quality=95)
            else:
                # Save as PNG
                pix.save(output_path)
            
            image_files.append(output_path)
            print(f"✓ Page {page_num + 1}/{total_pages}: {output_filename}")
        
        pdf_document.close()
        return image_files
        
    except Exception as e:
        print(f"Error converting PDF to images {pdf_path}: {e}")
        return []  # Return empty list if conversion fails

def process_files_or_urls(input_source, output_folder):
    """Process files/URLs and save as JSON with markdown content"""
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if not api_key:
        print("Error: Set LLAMA_CLOUD_API_KEY environment variable!")
        return
    
    os.makedirs(output_folder, exist_ok=True)
    
    parser = LlamaParse(
        api_key=api_key,
        num_workers=2,
        parse_mode="parse_page_with_agent",
        model="anthropic-sonnet-3.5",
        high_res_ocr=True,
        adaptive_long_table=True,
        outlined_table_extraction=True,
        output_tables_as_HTML=True,
        system_prompt_append="You are a parser. Your only task is to extract **English text only** from the input image. ",
        page_separator="\n\n---\n\n",
    )
    
    # Get files to process
    is_url = '://' in input_source
    if is_url:
        files_to_process = [input_source]
    else:
        extensions = ["*.pdf", "*.docx", "*.pptx", "*.xlsx", "*.xls", "*.html", "*.txt", "*.csv"]
        files_to_process = []
        for ext in extensions:
            files_to_process.extend(glob.glob(os.path.join(input_source, ext)))
        
        if not files_to_process:
            print(f"No files found in {input_source}")
            return
    
    # Create temporary directory for PDF image conversion
    temp_dir = tempfile.mkdtemp()
    
    try:
        for file_source in files_to_process:
            # Check if file is PDF and convert it to images
            if not is_url and file_source.lower().endswith('.pdf'):
                print(f"Converting PDF to images: {Path(file_source).name}")
                image_files = pdf_to_images(file_source, temp_dir)
                
                # Process all images from this PDF and combine into one JSON
                all_pages_data = []
                pdf_filename = Path(file_source).stem
                
                for page_num, image_file in enumerate(image_files, 1):
                    try:
                        print(f"Processing page {page_num}/{len(image_files)}: {Path(image_file).name}")
                        result = parser.parse(image_file)
                        
                        # Extract content from each page in the result
                        for page in result.pages:
                            all_pages_data.append({
                                "page": page_num,
                                "content": page.md
                            })
                            
                    except Exception as e:
                        print(f"✗ Error processing page {page_num}: {e}")
                        # Add empty page if processing fails
                        all_pages_data.append({
                            "page": page_num,
                            "content": f"Error processing page {page_num}: {e}"
                        })
                        continue
                
                # Save combined JSON for this PDF
                if all_pages_data:
                    output_data = {"pages": all_pages_data}
                    output_path = os.path.join(output_folder, f"{pdf_filename}.json")
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(output_data, f, ensure_ascii=False, indent=2)
                    
                    print(f"✓ {pdf_filename}.json - {len(all_pages_data)} pages combined")
                
            else:
                # Handle non-PDF files (single file processing)
                try:
                    result = parser.parse(file_source)
                    output_data = {"pages": [{"page": i, "content": page.md} for i, page in enumerate(result.pages, 1)]}
                    
                    # Generate filename
                    if is_url:
                        filename = Path(urllib.parse.urlparse(file_source).path).stem or f"url_{hash(file_source) % 10000}"
                    else:
                        filename = Path(file_source).stem
                    
                    output_path = os.path.join(output_folder, f"{filename}.json")
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(output_data, f, ensure_ascii=False, indent=2)
                    
                    print(f"✓ {filename}.json - {len(output_data['pages'])} pages")
                    
                except Exception as e:
                    print(f"✗ Error processing {Path(file_source).name}: {e}")
                    continue
    
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    input_source = "./input_files"
    output_folder = "/data"
    process_files_or_urls(input_source, output_folder)

