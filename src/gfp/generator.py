import importlib.util
import io
from pathlib import Path
from typing import cast, Any, Generic, Type, TypeVar

from jinja2 import Template, Environment, FileSystemLoader
from jsonasobj2 import as_dict
from linkml_runtime.utils.yamlutils import from_yaml, YAMLRoot

from gfp.model3 import Schema, TypeSpec


class ParserGenerator:
    def __init__(self, schema: Schema, target_folder = Path.cwd()):
        self.schema = schema
        self.target_folder = target_folder
        self.default_type = schema.meta.default_type
        self.default_delimiter = schema.meta.default_delimiter
        self.default_delimiter_repeating = schema.meta.default_delimiter_repeating

        # TODO this might be different for an installed package
        #  check if we can use the package resources module?
        template_dir = Path(__file__).parent / 'templates'
        self.jinja2_env = Environment(loader=FileSystemLoader(template_dir))

    def run(self):
        # file_template = Template((Path(__file__).parent / 'file.j2').read_text())
        file_template = self.jinja2_env.get_template('file.j2')
        # class_template = Template((Path(__file__).parent / 'class.j2').read_text())
        class_template = self.jinja2_env.get_template('class.j2')
        ctx = ParserGenerator.RecursionContext(self, self.schema, class_template)
        class_ = str(ctx)
        for class_ in [class_]:
            result = file_template.render({'classes': [class_], 'imports': self.schema.meta.imports})
            (self.target_folder / f'{self.schema.id}.py').write_text(result)


    class RecursionContext:
        def __init__(self, base, schema: TypeSpec | Schema, template: Template, parent = ''):
            self.base = base
            self.spec = schema
            self.template = template
            self._parent = parent
            self.inners = [
                ParserGenerator.RecursionContext(self.base, inner, template, self.fqdn)
                for inner in schema.types.values()
            ] if schema.types else []

        @property
        def fqdn(self) -> str:
            if self._parent:
                return f'{self._parent}.{self.spec.id}'
            return f'{self.spec.id}'

        def __str__(self):
            data = {
                'class_name': self.spec.id,
                'fqdn': self.fqdn,
                'steps': [
                    {
                        # **as_dict(field),
                        **field.model_dump(),
                        # 'type': field.type,
                        'delimiter': field.delimiter if field.delimiter is not None else self.base.default_delimiter,
                        'delimiter_repeating': (
                            field.delimiter_repeating
                            if field.delimiter_repeating is not None
                            else self.base.default_delimiter_repeating
                        ),
                        'type': field.type if field.type is not None else self.base.default_type,
                        'name': field.id,
                        'consume': field.consume if field.consume is not None else True
                    }
                    for field in self.spec.seq
                ],
                'inners': [
                    str(inner)
                    for inner in self.inners
                ],
                'instances': list(self.spec.instances.values()) if self.spec.instances is not None else []
                # 'default_type': self.base.default_type,
                # 'default_delimiter': self.base.default_delimiter,

            }
            return self.template.render(data)


AnyYAMLRoot = TypeVar('AnyYAMLRoot', bound=YAMLRoot)
def typed_from_yaml(source: Any, _t: Generic[AnyYAMLRoot]) -> AnyYAMLRoot:
    return cast(_t, from_yaml(source, _t))
