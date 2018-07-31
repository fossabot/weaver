#!/usr/bin/env cwl-runner

{
    'cwlVersion': 'v1.0',
    'class': 'CommandLineTool',
    'hints': {
        'DockerRequirement': {
            'dockerPull': 'docker-registry.crim.ca/ogc-public/debian8-snap6-gpt:v1'
        }
    },
    'inputs': {
        'file_type': {
            'inputBinding': {
                'position': 2,
                'prefix': '-f'
            },
            'type': 'string'
        },
        'source': {
            'inputBinding': {
                'position': 2,
                'prefix': '-SsourceProduct=',
                'separate': false
            },
            'type': 'File'
        },
        'output_name': {
            'inputBinding': {
                'position': 2,
                'prefix': '-t'
            },
            'type': 'string'
        },
        'source_graph': {
            'inputBinding': {
                'position': 1
            },
            'type': 'File'
        }
    },
    'outputs': {
        'output': {
            'outputBinding': {
                'glob': '$(inputs.output_name)'
            },
            'type': 'File'
        }
    }
}
