from typing import List, Dict, Tuple
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
import scrubadub


class LangpifySanitizationUtils:
    """Utility class for PII detection, anonymization, and marking"""
    
    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
    
    def detect_pii(self, text: str) -> List:
        """Detect PII using Presidio"""
        results = self.analyzer.analyze(text=text, language="en")
        return results
    
    def anonymize_pii(self, text: str) -> str:
        """Anonymize detected PII"""
        results = self.detect_pii(text)
        anonymized_text = self.anonymizer.anonymize(
            text=text, 
            analyzer_results=results
        ).text
        return anonymized_text
    
    def mark_pii(self, text: str) -> Tuple[str, List[Dict]]:
        """Mark PII with tags instead of removing"""
        results = self.detect_pii(text)
        marked_text = text
        markers = []
        
        # Process in reverse order to maintain positions
        for result in sorted(results, key=lambda x: x.start, reverse=True):
            entity_type = result.entity_type
            start, end = result.start, result.end
            original_text = text[start:end]
            
            marker = f"[{entity_type}]"
            marked_text = marked_text[:start] + marker + marked_text[end:]
            
            markers.append({
                'type': entity_type,
                'original': original_text,
                'position': (start, end)
            })
        
        return marked_text, markers
    
    def scrubadub_clean(self, text: str) -> str:
        """Additional cleaning with scrubadub"""
        return scrubadub.clean(text)