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

    is_feed = data.get('is_feed', False)
    job_id = service_manager.process_podcast(data['url'], is_feed)
    
    return jsonify({
        'job_id': job_id,
        'status': 'queued',
        'message': f'{"Feed" if is_feed else "Episode"} processing has been queued'
    }), 202

@podcast_bp.route('/podcast/status/<job_id>', methods=['GET'])
def get_podcast_status(job_id):
    status = service_manager.get_job_status(job_id)
    if not status:
        return jsonify({'error': 'Job not found'}), 404
    
    # If this is a feed, include episode processing progress
    if status.get('is_feed') and status.get('feed_metadata'):
        total = status['feed_metadata'].get('total_episodes', 0)
        processed = status['feed_metadata'].get('processed_episodes', 0)
        status['progress'] = {
            'total_episodes': total,
            'processed_episodes': processed,
            'percentage': (processed / total * 100) if total > 0 else 0
        }
    
    return jsonify(status), 200

@podcast_bp.route('/podcast/history', methods=['GET'])
def get_processing_history():
    jobs = service_manager.get_processing_history()
    
    # Group episodes under their parent feeds if applicable
    organized_jobs = []
    feed_jobs = {}
    
    for job in jobs:
        if job.get('is_feed'):
            feed_jobs[job['job_id']] = job
            job['episodes'] = []
            organized_jobs.append(job)
        elif job.get('feed_metadata') and job['feed_metadata'].get('parent_job_id') in feed_jobs:
            parent_id = job['feed_metadata']['parent_job_id']
            feed_jobs[parent_id]['episodes'].append(job)
        else:
            organized_jobs.append(job)
    
    return jsonify({
        'jobs': organized_jobs,
        'total': len(organized_jobs)
    }), 200

@podcast_bp.route('/podcast/feed/episodes/<job_id>', methods=['GET'])
def get_feed_episodes(job_id):
    """Get all episodes for a specific feed job"""
    episodes = service_manager.get_feed_episodes(job_id)
    if episodes is None:
        return jsonify({'error': 'Feed job not found'}), 404
    
    return jsonify({
        'episodes': episodes,
        'total': len(episodes)
    }), 200 