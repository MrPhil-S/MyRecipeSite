"""Small stdlib-only HTML form parser shared with operational smoke tooling."""

from html.parser import HTMLParser


class FormParser(HTMLParser):
    """Collect successful HTML form controls as ordered ``(name, value)`` pairs."""

    def __init__(self, body):
        super().__init__()
        self.fields = []
        self.textarea = None
        self.select = None
        self.option = None
        self.feed(body)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        name = attrs.get('name')
        if tag == 'input' and name and attrs.get('type') != 'file':
            if attrs.get('type') not in ('checkbox', 'radio') or 'checked' in attrs:
                self.fields.append((name, attrs.get('value', '')))
        if tag == 'textarea' and name:
            self.textarea = [name, '']
        if tag == 'select' and name:
            self.select = {'name': name, 'options': [], 'multiple': 'multiple' in attrs}
        if tag == 'option' and self.select:
            self.option = [attrs.get('value', ''), 'selected' in attrs]

    def handle_data(self, data):
        if self.textarea:
            self.textarea[1] += data

    def handle_endtag(self, tag):
        if tag == 'textarea' and self.textarea:
            self.fields.append(tuple(self.textarea))
            self.textarea = None
        if tag == 'option' and self.select and self.option:
            self.select['options'].append(self.option)
            self.option = None
        if tag == 'select' and self.select:
            selected = [option[0] for option in self.select['options'] if option[1]]
            if not selected and not self.select['multiple'] and self.select['options']:
                selected = [self.select['options'][0][0]]
            self.fields.extend((self.select['name'], value) for value in selected)
            self.select = None
