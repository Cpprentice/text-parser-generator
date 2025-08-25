import importlib.resources
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import cast, Any, Generic, TypeVar

from jinja2 import Template, Environment, FileSystemLoader
from linkml_runtime.utils.yamlutils import from_yaml, YAMLRoot
from pydantic import RootModel

from text_parser_generator.model import ParserSchemaSpecification, TypeSpec, Attribute


class TextParserGenerator:
    def __init__(self, schema: ParserSchemaSpecification, target_folder = Path.cwd()):
        self.schema = schema
        self.target_folder = target_folder
        self.default_type = schema.meta.default_type
        self.default_delimiter = schema.meta.default_delimiter
        self.default_delimiter_repeating = schema.meta.default_delimiter_repeating

        template_dir = importlib.resources.files('text_parser_generator') / 'templates'
        self.jinja2_env = Environment(loader=FileSystemLoader(template_dir))
        self.jinja2_env.globals.update(zip=zip)  # inject the zip method in templates

    def run(self):
        file_template = self.jinja2_env.get_template('file.j2')
        class_template = self.jinja2_env.get_template('class.j2')
        slot_template = self.jinja2_env.get_template('step.j2')
        instance_template = self.jinja2_env.get_template('instance.j2')
        ctx = TextParserGenerator.RecursionContext(self, self.schema, class_template, slot_template, instance_template)
        class_ = str(ctx)
        for class_ in [class_]:
            result = file_template.render({
                'classes': [class_],
                'imports': self.schema.meta.imports if self.schema.meta.imports is not None else []
            })
            (self.target_folder / f'{self.schema.id}.py').write_text(result)

    def load_module(self) -> ModuleType:
        spec = importlib.util.spec_from_file_location('schema', self.target_folder / f'{self.schema.id}.py')
        schema_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(schema_module)
        return schema_module

    class RecursionContext:
        def __init__(
                self,
                base,
                schema: TypeSpec | ParserSchemaSpecification,
                class_template: Template,
                slot_template: Template,
                instance_template: Template,
                parent = ''
        ):
            self.base = base
            self.spec = schema
            self.class_template = class_template
            self.slot_template = slot_template
            self.instance_template = instance_template
            self._parent = parent
            self.inners = [
                TextParserGenerator.RecursionContext(self.base, inner, class_template,
                                                 slot_template, instance_template, self.fqdn)
                for inner in schema.types.values()
            ] if schema.types else []

        @property
        def fqdn(self) -> str:
            if self._parent:
                return f'{self._parent}.{self.spec.id}'
            return f'{self.spec.id}'

        def __str__(self):
            step_data = {
                'steps': [
                    {
                        **field.model_dump(),
                        'delimiter': field.delimiter if field.delimiter is not None else self.base.default_delimiter,
                        'delimiter_repeating': (
                            field.delimiter_repeating
                            if field.delimiter_repeating is not None
                            else self.base.default_delimiter_repeating
                        ),
                        'type': (field.type.root if isinstance(field.type, RootModel) else field.type) \
                            if field.type is not None else self.base.default_type,
                        'name': field.id,
                        'consume': field.consume if field.consume is not None else True
                    }
                    for field in self.spec.seq
                ]
            }

            rendered_slots = [
                self.slot_template.render({
                    'class_name': self.spec.id,
                    'fqdn': self.fqdn,
                    'step': step
                }).lstrip()
                for step in step_data['steps']
            ]

            instance_data = {
                'instances': [
                    {
                        **field.model_dump(),
                        'delimiter': field.delimiter if field.delimiter is not None else self.base.default_delimiter,
                        'delimiter_repeating': (
                            field.delimiter_repeating
                            if field.delimiter_repeating is not None
                            else self.base.default_delimiter_repeating
                        ),
                        'type': (field.type.root if isinstance(field.type, RootModel) else field.type) \
                            if field.type is not None else self.base.default_type,
                        'name': field.id,
                        'consume': field.consume if field.consume is not None else True
                    }
                    for field in self.spec.instances.values()
                ] if self.spec.instances is not None else []
            }

            rendered_instances = [
                self.instance_template.render({
                    'class_name': self.spec.id,
                    'fqdn': self.fqdn,
                    'instance': instance
                }).lstrip()
                for instance in instance_data['instances']
            ]

            data = {
                'class_name': self.spec.id,
                'fqdn': self.fqdn,
                'params': self.spec.params or [],
                **step_data,
                'rendered_steps': rendered_slots,
                'inners': [
                    str(inner)
                    for inner in self.inners
                ],
                **instance_data,
                'rendered_instances': rendered_instances,
                # 'instances': list(self.spec.instances.values()) if self.spec.instances is not None else []
                # 'default_type': self.base.default_type,
                # 'default_delimiter': self.base.default_delimiter,

            }
            return self.class_template.render(data)


def fix_types_schema(schema: ParserSchemaSpecification):

    def traverse(obj):
        if hasattr(obj, 'types') and obj.types is not None:
            obj.types = {
                key: TypeSpec(id=key, **value)
                for key, value in obj.types.items()
            }
            for subtype in obj.types.values():
                traverse(subtype)

    traverse(schema)

def fix_instances_schema(schema: ParserSchemaSpecification):
    def traverse(obj):
        if hasattr(obj, 'instances') and obj.instances is not None:
            obj.instances = {
                key: Attribute(id=key, **value)
                for key, value in obj.instances.items()
            }
        if hasattr(obj, 'types') and obj.types is not None:
            for subtype in obj.types.values():
                traverse(subtype)
    traverse(schema)


AnyYAMLRoot = TypeVar('AnyYAMLRoot', bound=YAMLRoot)
def typed_from_yaml(source: Any, _t: Generic[AnyYAMLRoot]) -> AnyYAMLRoot:
    result = cast(_t, from_yaml(source, _t))
    return result


def load_specification_from_yaml(source: Any) -> ParserSchemaSpecification:
    spec = typed_from_yaml(source, ParserSchemaSpecification)
    fix_types_schema(spec)
    fix_instances_schema(spec)
    return spec
