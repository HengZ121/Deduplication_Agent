import unittest
import xml.etree.ElementTree as ET
from count_dita_file_words import content_text, word_tokens


class FileWordCountTests(unittest.TestCase):
    def count(self, xml):
        return len(word_tokens(content_text(ET.fromstring(xml))))

    def test_titles_body_and_tail_without_metadata(self):
        self.assertEqual(self.count('<topic id="ignored"><title>Two words</title><prolog><author>Ignore me</author></prolog><body><p>One <b>two</b> three.</p></body></topic>'), 5)

    def test_references_do_not_count_attributes_or_expand(self):
        self.assertEqual(self.count('<topic><body><p conref="other.dita#id"/><xref href="a.dita">Read this</xref></body></topic>'), 2)

    def test_unicode_and_empty_body(self):
        self.assertEqual(self.count('<topic><body><p>L’enfant reçoit vingt-deux euros.</p></body></topic>'), 4)
        self.assertEqual(self.count('<topic><body/></topic>'), 0)


if __name__ == '__main__': unittest.main()
