from flask import Flask, render_template, jsonify, request, session, url_for, redirect
import firebase_admin
from firebase_admin import credentials, db
import requests
import os
import json
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a-very-secret-key-for-development-only')

# --- Google OAuth Configuration ---
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', '367711020009-o70b96v4cv604acg2hqv60k8c5mjmhtr.apps.googleusercontent.com')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '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')
app.config['GOOGLE_DISCOVERY_URL'] = (
    'https://accounts.google.com/.well-known/openid-configuration'
)

oauth = OAuth(app)

oauth.register(
    'google',
    client_id=app.config.get('GOOGLE_CLIENT_ID'),
    client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url=app.config.get('GOOGLE_DISCOVERY_URL'),
    client_kwargs={'scope': 'openid email profile'},
)

# --- Firebase Initialization ---
cred_path = os.path.join(os.path.dirname(__file__), 'firebase.json')
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://forum-44dbd-default-rtdb.firebaseio.com/'
})

# --- Constants ---
TMDB_API_KEY = 'fb7bb23f03b6994dafc674c074d01761'
TMDB_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/original'
DATA_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data.json')

# --- Genre Maps (Hebrew) ---
GENRE_MAP_MOVIE = {
    28: 'פעולה', 12: 'הרפתקאות', 16: 'אנימציה', 35: 'קומדיה', 80: 'פשע',
    99: 'דוקומנטרי', 18: 'דרמה', 10751: 'משפחה', 14: 'פנטזיה', 36: 'היסטוריה',
    27: 'אימה', 10402: 'מוזיקה', 9648: 'מסתורין', 10749: 'רומנטיקה',
    878: 'מדע בדיוני', 10770: 'סרט טלוויזיה', 53: 'מותחן', 10752: 'מלחמה', 37: 'מערבון'
}
GENRE_MAP_TV = {
    10759: 'פעולה והרפתקאות', 16: 'אנימציה', 35: 'קומדיה', 80: 'פשע',
    99: 'דוקומנטרי', 18: 'דרמה', 10751: 'משפחה', 10762: 'ילדים',
    9648: 'מסתורין', 10763: 'חדשות', 10764: 'ריאליטי', 10765: 'מדע בדיוני ופנטזיה',
    10766: 'אופרת סבון', 10767: 'אירוח', 10768: 'מלחמה ופוליטיקה', 37: 'מערבון'
}

# --- Data Caching Function ---
def update_data_json_from_db():
    print("Attempting to update data.json from Firebase...")
    categories_ref = db.reference('categories')
    categories_dict = categories_ref.get() or {}
    category_map = {cat_id: cat_data.get('name', 'לא ידוע') for cat_id, cat_data in categories_dict.items()}

    anime_ref = db.reference('anime')
    all_anime_dict = anime_ref.get() or {}

    all_anime_list = []
    for key, value in all_anime_dict.items():
        value['id'] = key
        category_id = value.get('categoryId')
        value['categoryName'] = category_map.get(category_id, 'ללא קטגוריה')
        all_anime_list.append(value)
    
    with open(DATA_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_anime_list, f, ensure_ascii=False, indent=2)
    print("data.json has been updated successfully with category information.")


# --- Authentication Routes ---

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = oauth.google.authorize_access_token()
    user_info = oauth.google.parse_id_token(token)
    session['user'] = user_info
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


# --- HTML Rendering Routes ---

@app.route('/')
def index():
    return render_template('index.html', user=session.get('user'))

@app.route('/manage')
def manage():
    if 'user' not in session or session['user'].get('email') != 'ehudverbin@gmail.com':
        return redirect(url_for('index'))
    return render_template('manage.html', user=session.get('user'))

@app.route('/movies')
def movies_page():
    return render_template('movies.html', user=session.get('user'))

@app.route('/shows')
def shows_page():
    return render_template('shows.html', user=session.get('user'))


# --- API Routes: Categories ---

@app.route('/api/categories', methods=['GET'])
def get_categories():
    ref = db.reference('categories')
    categories = ref.get()
    if not categories:
        return jsonify([])
    categories_list = [{'id': key, 'name': value['name']} for key, value in categories.items()]
    return jsonify(categories_list)

@app.route('/api/categories', methods=['POST'])
def add_category():
    data = request.json
    category_name = data.get('name')
    if not category_name:
        return jsonify({'error': 'שם קטגוריה הוא שדה חובה'}), 400
    
    try:
        ref = db.reference('categories')
        ref.push({'name': category_name})
        return jsonify({'success': True, 'message': f'קטגוריה "{category_name}" נוצרה בהצלחה!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- API Routes: Content (Anime/Movies/Shows) ---

@app.route('/api/anime')
def get_anime():
    try:
        with open(DATA_JSON_PATH, 'r', encoding='utf-8') as f:
            all_anime_list = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        update_data_json_from_db()
        try:
            with open(DATA_JSON_PATH, 'r', encoding='utf-8') as f:
                all_anime_list = json.load(f)
        except:
             return jsonify([])

    anime_type = request.args.get('type', 'all')
    search = request.args.get('search', '').lower()
    genre = request.args.get('genre', 'all')
    
    filtered = all_anime_list
    
    if anime_type != 'all':
        filtered = [a for a in filtered if a.get('type') == anime_type]
    
    if search:
        filtered = [
            a for a in filtered 
            if search in a.get('title', '').lower() or search in a.get('title_he', '').lower()
        ]
    
    if genre != 'all':
        filtered = [a for a in filtered if a.get('genre') and genre in a['genre']]
    
    return jsonify(filtered)

@app.route('/api/anime/<anime_id>')
def get_anime_details(anime_id):
    ref = db.reference(f'anime/{anime_id}')
    anime = ref.get()
    if anime:
        anime['id'] = anime_id
        return jsonify(anime)
    return jsonify({'error': 'לא נמצא'}), 404

@app.route('/api/search_external')
def search_external():
    query = request.args.get('query')
    search_type = request.args.get('type', 'tv')
    if not query:
        return jsonify({'error': 'Query parameter is required'}), 400

    url = f"{TMDB_BASE_URL}/search/{search_type}?api_key={TMDB_API_KEY}&query={query}&language=he-IL&include_adult=false"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get('results', []):
            if search_type == 'tv':
                title = item.get('name')
                year = item.get('first_air_date', '----').split('-')[0]
            else:
                title = item.get('title')
                year = item.get('release_date', '----').split('-')[0]

            results.append({
                'id': item.get('id'),
                'title': title,
                'year': year,
                'poster': f"{TMDB_IMAGE_BASE_URL}{item.get('poster_path')}" if item.get('poster_path') else None,
                'overview': item.get('overview')
            })
        return jsonify(results)
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/add_content', methods=['POST'])
def add_content():
    data = request.json
    content_type = data.get('type')
    
    if not content_type:
        return jsonify({'error': 'Content type is required'}), 400

    if content_type == 'episode':
        series_id = data.get('series_id')
        season_num = data.get('season')
        episode_num = data.get('episode')
        video_url = data.get('video_url')
        
        if not all([series_id, season_num, episode_num, video_url]):
            return jsonify({'error': 'Missing data for episode'}), 400
            
        try:
            ref = db.reference(f'anime/{series_id}/seasons/{season_num}/episodes/{episode_num}')
            ref.set({'video_url': video_url})
            return jsonify({'success': True, 'message': f'פרק {episode_num} נוסף לעונה {season_num}'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    else:
        tmdb_id = data.get('tmdb_id')
        category_id = data.get('category_id')

        if not tmdb_id or not category_id:
             return jsonify({'error': 'TMDB ID and Category ID are required'}), 400

        tmdb_api_type = 'tv' if content_type == 'series' else 'movie'
        url = f"{TMDB_BASE_URL}/{tmdb_api_type}/{tmdb_id}?api_key={TMDB_API_KEY}&language=he-IL"
        try:
            response = requests.get(url)
            response.raise_for_status()
            details = response.json()

            genre_map = GENRE_MAP_TV if content_type == 'series' else GENRE_MAP_MOVIE
            genres = [genre_map.get(g['id'], g['name']) for g in details.get('genres', [])]
            
            common_data = {
                'id': details.get('id'),
                'title': details.get('original_title') or details.get('original_name'),
                'title_he': details.get('title') or details.get('name'),
                'type': content_type,
                'rating': round(details.get('vote_average', 0), 1),
                'image': f"{TMDB_IMAGE_BASE_URL}{details.get('poster_path')}" if details.get('poster_path') else '',
                'banner': f"{TMDB_IMAGE_BASE_URL}{details.get('backdrop_path')}" if details.get('backdrop_path') else '',
                'genre': genres,
                'description': details.get('overview', ''),
                'categoryId': category_id
            }

            if content_type == 'series':
                common_data['year'] = details.get('first_air_date', '----').split('-')[0]
                common_data['episodes'] = details.get('number_of_episodes', 0)
                if not db.reference(f'anime/{tmdb_id}/seasons').get():
                    common_data['seasons'] = {}
            else:
                common_data['year'] = details.get('release_date', '----').split('-')[0]
                common_data['duration'] = details.get('runtime', 0)
                common_data['video_url'] = data.get('video_url', '')

            ref = db.reference(f'anime/{tmdb_id}')
            ref.update(common_data)
            
            update_data_json_from_db()
            return jsonify({'success': True, 'message': f'"{common_data["title_he"]}" נוסף בהצלחה!'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


# --- API Routes: System & Cache ---

@app.route('/api/update_json_cache', methods=['POST'])
def update_json_cache():
    try:
        update_data_json_from_db()
        return jsonify({'success': True, 'message': 'קובץ המידע עודכן בהצלחה מה-Database'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- App Startup ---
if __name__ == '__main__':
    if not os.path.exists(DATA_JSON_PATH):
        update_data_json_from_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
