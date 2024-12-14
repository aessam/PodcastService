from flask import Blueprint, jsonify, request
from pathlib import Path
from ...service.pipeline.service_manager import ServiceManager

podcast_bp = Blueprint('podcast', __name__)
service_manager = ServiceManager(Path("data"))
service_manager.start_workers()  # Start workers when the blueprint is created

@podcast_bp.route('/podcast/process', methods=['POST'])
def process_podcast():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400

    job_id = service_manager.process_podcast(data['url'])
    return jsonify({
        'job_id': job_id,
        'status': 'queued',
        'message': 'Podcast processing has been queued'
    }), 202

@podcast_bp.route('/podcast/status/<job_id>', methods=['GET'])
def get_podcast_status(job_id):
    status = service_manager.get_job_status(job_id)
    if not status:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(status), 200

@podcast_bp.route('/podcast/history', methods=['GET'])
def get_processing_history():
    jobs = service_manager.get_processing_history()
    return jsonify({
        'jobs': jobs,
        'total': len(jobs)
    }), 200 