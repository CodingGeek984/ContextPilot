from flask import jsonify

from services.analyzer_service import analyze_project


class AnalysisController:
    """Triggers the static repository analyzer and reports what changed."""

    @staticmethod
    def analyze(project_id: int, paths=None, full: bool = False):
        try:
            result = analyze_project(project_id, paths=paths, full=full)
        except LookupError as error:
            return jsonify({'error': str(error)}), 404
        except NotADirectoryError:
            return jsonify({
                'error': 'Project folder is not accessible',
                'details': 'The registered path does not exist or is not a directory.',
            }), 409
        except ValueError as error:
            return jsonify({'error': str(error)}), 400

        return jsonify(result), 200
