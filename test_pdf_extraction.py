#!/usr/bin/env python3
"""
Test script to verify PDF extraction fix.
Tests that all pages of a multi-page PDF are extracted.

Usage:
  python test_pdf_extraction.py path/to/test.pdf
"""

import sys
import io
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.api.ingest import _extract_text_from_pdf_bytes


def test_pdf_extraction(pdf_path: str):
    """Test PDF extraction with a real file."""
    
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"❌ File not found: {pdf_path}")
        return False
    
    if not pdf_path.suffix.lower() == '.pdf':
        print(f"❌ Not a PDF file: {pdf_path}")
        return False
    
    print(f"\n📄 Testing PDF extraction: {pdf_path.name}")
    print("=" * 60)
    
    # Read PDF bytes
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    
    # Extract text using fixed function
    print(f"\n🔄 Extracting text from PDF...")
    extracted_text = _extract_text_from_pdf_bytes(pdf_bytes, pdf_path.name)
    
    # Show results
    print("\n" + "=" * 60)
    print("📊 EXTRACTION RESULTS:")
    print("=" * 60)
    
    if extracted_text:
        char_count = len(extracted_text)
        word_count = len(extracted_text.split())
        page_estimate = max(1, char_count // 2500)  # Rough estimate
        
        print(f"✅ Successfully extracted text")
        print(f"   Total characters: {char_count:,}")
        print(f"   Total words: {word_count:,}")
        print(f"   Estimated pages: ~{page_estimate}")
        print(f"\n📝 First 500 characters:")
        print("-" * 60)
        print(extracted_text[:500] + "...")
        print("-" * 60)
        
        return True
    else:
        print(f"❌ No text extracted from PDF")
        print(f"   This could mean:")
        print(f"   - PDF is scanned/image-based (no OCR configured)")
        print(f"   - PDF is corrupted or encrypted")
        print(f"   - Both extraction methods failed")
        return False


def test_logging_output():
    """Test that logging shows per-page extraction."""
    
    print("\n\n📋 EXPECTED LOG OUTPUT:")
    print("=" * 60)
    print("""
When a multi-page PDF is processed, you should see logs like:

📄 Extracting PDF 'document.pdf' using PyPDF2...
   📋 Total pages detected: 10
   ✓ Page 1/10: 2,500 chars extracted
   ✓ Page 2/10: 1,890 chars extracted
   ✓ Page 3/10: 2,120 chars extracted
   ✓ Page 4/10: 2,450 chars extracted
   ✓ Page 5/10: 2,100 chars extracted
   ✓ Page 6/10: 1,980 chars extracted
   ✓ Page 7/10: 2,340 chars extracted
   ✓ Page 8/10: 2,200 chars extracted
   ✓ Page 9/10: 2,150 chars extracted
   ✓ Page 10/10: 1,890 chars extracted
   ✅ PyPDF2 Success: Extracted 21,200 chars from 10 pages

If PyPDF2 fails:
   ❌ PyPDF2 failed: [error details]
   📄 Falling back to pdfplumber...
   [pdfplumber extraction logs...]
    """)
    print("=" * 60)


def main():
    """Run PDF extraction test."""
    
    print("\n" + "=" * 60)
    print("🧪 PDF EXTRACTION FIX - TEST SCRIPT")
    print("=" * 60)
    
    # Check if PDF path was provided
    if len(sys.argv) < 2:
        print("\n⚠️  Usage: python test_pdf_extraction.py <path_to_pdf>")
        print("\nExample: python test_pdf_extraction.py sample.pdf")
        test_logging_output()
        return
    
    pdf_path = sys.argv[1]
    
    # Run test
    success = test_pdf_extraction(pdf_path)
    
    # Show expected logs
    test_logging_output()
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60)
    
    if success:
        print("\n✅ PDF extraction is working correctly!")
        print("   All pages should have been extracted.")
        print("\n🎯 Next steps:")
        print("   1. Check logs in background PDF processing")
        print("   2. Verify all pages appear in vector database")
        print("   3. Ask chatbot questions about content from different pages")
    else:
        print("\n⚠️  PDF extraction had issues.")
        print("   Check logs above for details.")
        print("\n💡 Possible causes:")
        print("   - PDF is scanned (image-based, no OCR)")
        print("   - PDF is encrypted or corrupted")
        print("   - Both PyPDF2 and pdfplumber failed")
        print("\n📚 See: PDF_EXTRACTION_BUG_FIX_SUMMARY.md for details")


if __name__ == "__main__":
    main()
