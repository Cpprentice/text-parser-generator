import collections
import itertools
import json
import re
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
# from simpleeval import simple_eval

from text_parser_generator.parser import re_search
from text_parser_generator.generator import typed_from_yaml, TextParserGenerator
from text_parser_generator.model import ParserSchemaSpecification


def get_test_case_root_dir() -> Path:
    return Path(__file__).parent.parent.parent.parent / 'data' / 'rscad' / 'COMPONENTS'

def get_test_file_paths() -> list[Path]:
    base_path = get_test_case_root_dir()
    return [p for p in base_path.rglob('*') if p.is_file() and p.suffix in {'.def', ''} and not 'OBSOLETE' in p.parts]


def get_test_file_ids() -> list[str]:
    file_paths = get_test_file_paths()
    base_path = get_test_case_root_dir()
    return [f'_{path.relative_to(base_path)}' for path in file_paths]


@pytest.fixture
def rscad_parser_module() -> ModuleType:
    with tempfile.TemporaryDirectory() as directory:
        conf: ParserSchemaSpecification = typed_from_yaml((Path(__file__).parent / 'parser-spec.yaml').read_text(), ParserSchemaSpecification)
        generator = TextParserGenerator(conf, target_folder=Path(directory))
        generator.run()
        schema_module = generator.load_module()
        yield schema_module


def local_parser_module() -> ModuleType:
    conf: ParserSchemaSpecification = typed_from_yaml((Path(__file__).parent / 'parser-spec.yaml').read_text(), ParserSchemaSpecification)
    generator = TextParserGenerator(conf)
    generator.run()
    schema_module = generator.load_module()
    return schema_module


@pytest.mark.parametrize('file_path', get_test_file_paths(), ids=get_test_file_ids())
def test_rscad_component_library_files(rscad_parser_module: ModuleType, file_path: Path):
    with open(file_path, 'rb') as stream:
        schema = rscad_parser_module.RSCADDefinition(stream)


def test_rscad_control_relay(rscad_parser_module: ModuleType):
    file_path = Path(__file__).parent / '_rtds_PN_5051_67_46'
    with open (file_path, 'rb') as stream:
        schema = rscad_parser_module.RSCADDefinition(stream)
        _ = schema.sections
        _ = 42


def test_rscad_dynamic_load():
    conf: ParserSchemaSpecification = typed_from_yaml((Path(__file__).parent / 'parser-spec.yaml').read_text(), ParserSchemaSpecification)
    generator = TextParserGenerator(conf)
    generator.run()
    schema_module = generator.load_module()

    file_path = Path(__file__).parent / 'rtds_udc_DYLOAD'
    with open(file_path, 'rb') as stream:
        test_schema = schema_module.RSCADDefinition(stream)

        _ = test_schema.sections
        _ = _[5].body.parameter_groups
        _ = test_schema.sections[6].body.statements[0]  # first if statement
        conditions = _.statement_body.conditions
        blocks = _.statement_body.statement_blocks

        # section_strings = [
        #     # section_stream.read(section_stream.size)
        #     section_stream.read()
        #     for section_stream in test_schema._raw_sections
        # ]
        assert test_schema.section_count == 22

    file_path = Path(__file__).parent / 'rtds_vsc_DYNLOAD'
    with open(file_path, 'rb') as stream:
        test_schema2 = schema_module.RSCADDefinition(stream)
        _ = 42

        variable_search_pattern = re.compile(r'\b(?!true\b)(?!false\b)[a-z_][a-z0-9_]+\b', re.IGNORECASE)
        all_variables = []
        for condition_string in test_schema2.sections[3].body.all_conditions:
            all_variables.extend(re.findall(variable_search_pattern, condition_string))
        all_variable_set = set(all_variables)

        def produce_relevant_graphics_statement(data: dict[str, Any], graphics_section_body) -> list[str]:
            if not all(x in all_variable_set for x in data):
                raise ValueError('Data set is not complete')

            def keep_statement(statement) -> bool:
                return statement.statement_type.lower() in {'box', 'line'}

            def recurse_statement(statement) -> bool:
                return statement.statement_type.lower() == 'if'

            def recursor(if_statement) -> list:
                statements = []
                # simple_eval = lambda *args, **kwargs: True
                for i, condition in enumerate(if_statement.statement_body.conditions):
                    # check if condition is parenthesis syntax (a,b)
                    parenthesis_syntax = re.match(r'\([^,]+,[^,]+\)', condition.strip())
                    if parenthesis_syntax:
                        condition = f' == '.join(condition.strip()[1:-1].split(','))
                    if simple_eval(condition, names=data):
                        for statement in if_statement.statement_body.statement_blocks[i]:
                            if keep_statement(statement):
                                print(f'{statement.statement_type}({statement.statement_body._pieces})')
                                statements.append(statement)
                            elif recurse_statement(statement):
                                statements.extend(recursor(statement))
                        # break  # TODO add this again after testing
                return statements

            results = []
            for statement in graphics_section_body.statements:
                if keep_statement(statement):
                    print(f'{statement.statement_type}({statement.statement_body._pieces})')
                    results.append(statement)
                elif recurse_statement(statement):
                    results.extend(recursor(statement))
            return results


        data = {
            'nmbr': 3,
            'conn1': 1,
            'frc1': 0,
            'frc2': 0,
            'frc3': 0,
            'mon1': 0,
            'mon2': 0,
            'mon3': 0,
        }
        statements = produce_relevant_graphics_statement(data, test_schema2.sections[3].body)
        with open('statements.json', 'w') as stream:
            json.dump([(x.statement_type, x.statement_body._pieces) for x in statements], stream, indent=4)

        positions = [x.statement_body._pieces for x in statements]
        # at the moment positions is way too small - it should be 118 i believe. Now fixed
        bounding_box = (
            min(min([int(pos[0]) for pos in positions]), min([int(pos[2]) for pos in positions])),
            min(min([int(pos[1]) for pos in positions]), min([int(pos[3]) for pos in positions])),
            max(max([int(pos[0]) for pos in positions]), max([int(pos[2]) for pos in positions])),
            max(max([int(pos[1]) for pos in positions]), max([int(pos[3]) for pos in positions])),
        )
        def is_line_horizontal(pos: tuple[int, int, int, int]) -> bool:
            return pos[1] == pos[3]

        def is_line_vertical(pos: tuple[int, int, int, int]) -> bool:
            return pos[0] == pos[2]

        int_positions = [(int(x0), int(y0), int(x1), int(y1)) for x0, y0, x1, y1 in positions]

        def does_touch_bounding_box(box: tuple[int, int, int, int], pos: tuple[int, int]) -> bool:
            return pos[0] in {box[0], box[2]} or pos[1] in {box[1], box[3]}

        def get_touch_points(positions: list[tuple[int, int, int, int]], bounding_box: tuple[int, int, int, int]) -> list[tuple[int, int]]:
            results = []
            for pos in positions:
                if is_line_vertical(pos):
                    start_point = (pos[0], pos[1])
                    middle_point = (pos[0], int((pos[1] + pos[3]) / 2))
                    end_point = (pos[2], pos[3])
                    if not does_touch_bounding_box(bounding_box, middle_point):
                        if does_touch_bounding_box(bounding_box, start_point):
                            results.append(start_point)
                        if does_touch_bounding_box(bounding_box, end_point):
                            results.append(end_point)
                elif is_line_horizontal(pos):
                    start_point = (pos[0], pos[1])
                    middle_point = (int((pos[0] + pos[2]) / 2), pos[1])
                    end_point = (pos[2], pos[3])
                    if not does_touch_bounding_box(bounding_box, middle_point):
                        if does_touch_bounding_box(bounding_box, start_point):
                            results.append(start_point)
                        if does_touch_bounding_box(bounding_box, end_point):
                            results.append(end_point)
            return results
        touch_points = get_touch_points(int_positions, bounding_box)
        _ = 42


if __name__ == '__main__':
    # test_rscad_dynamic_load()
    test_rscad_control_relay(local_parser_module())
    _ = re_search.history
    length_histograms = {
        exp: collections.Counter(lengths)
        for exp, lengths in _.items()
    }
    breakpoints = {exp: {value: key for key, value in counter.items()} for exp, counter in length_histograms.items()}
    x = 42

