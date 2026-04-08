from flask import Flask, render_template, session, redirect, url_for, request
import json
import random
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# 题型配置
QUESTION_CONFIG = {
    'single': {'count': 12, 'score': 5},
    'multiple': {'count': 5, 'score': 6},
    'text': {'count': 2, 'score': 5}
}
BANK_FILES = ['bank1.json', 'bank2.json', 'bank3.json', 'bank4.json']
DATA_DIR = 'data'

CANDIDATES = {
    '李光耀': '123456',
    '罗楷聪': '123456',
    '邓志超': '123456',
    '林雅纯': '123456',
    '周新东': '123456',
    '崖恒远': '123456',
    '李汉尧': '123456'
}

def load_all_questions():
    pool = {'single': [], 'multiple': [], 'text': []}
    for filename in BANK_FILES:
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            bank = json.load(f)
            for q in bank['questions']:
                q_type = q.get('type', 'single')
                if q_type == 'practical':
                    continue
                if q_type in pool:
                    if 'scored' not in q:
                        q['scored'] = True
                    pool[q_type].append(q)
    return pool

def filter_true_multiples(questions):
    true_multi, fake_multi = [], []
    for q in questions:
        ans = q.get('answer', '').strip().upper()
        ans_clean = ans.replace(',', '').replace(' ', '')
        if len(ans_clean) > 1:
            true_multi.append(q)
        else:
            fake_multi.append(q)
    return true_multi, fake_multi

def generate_paper():
    pool = load_all_questions()
    selected = []
    
    single_pool = pool.get('single', [])
    single_count = min(QUESTION_CONFIG['single']['count'], len(single_pool))
    if single_count > 0:
        selected.extend(random.sample(single_pool, single_count))
    
    multi_pool = pool.get('multiple', [])
    true_multi, fake_multi = filter_true_multiples(multi_pool)
    target_multi = QUESTION_CONFIG['multiple']['count']
    if len(true_multi) >= target_multi:
        sampled_multi = random.sample(true_multi, target_multi)
    else:
        sampled_multi = true_multi.copy()
        remaining = target_multi - len(sampled_multi)
        if remaining > 0 and fake_multi:
            sampled_multi.extend(random.sample(fake_multi, min(remaining, len(fake_multi))))
    selected.extend(sampled_multi)
    
    text_pool = pool.get('text', [])
    text_count = min(QUESTION_CONFIG['text']['count'], len(text_pool))
    if text_count > 0:
        selected.extend(random.sample(text_pool, text_count))
    
    return selected

def check_single(user_ans, correct_ans):
    return user_ans.strip().upper() == correct_ans.strip().upper()

def check_multiple(user_ans, correct_ans):
    if not user_ans:
        return False
    user_set = set(user_ans.upper().replace(',', '').replace(' ', ''))
    correct_set = set(correct_ans.upper().replace(',', '').replace(' ', ''))
    return user_set == correct_set

def check_text(user_ans, keywords, full_score):
    if not user_ans or not keywords:
        return 0.0
    user_lower = user_ans.lower()
    matched = sum(1 for kw in keywords if kw.lower() in user_lower)
    return (matched / len(keywords)) * full_score

@app.errorhandler(405)
def method_not_allowed(e):
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '').strip()
        if name in CANDIDATES and CANDIDATES[name] == password:
            if session.get(f'exam_done_{name}', False):
                return render_template('login.html', error='您已完成考试，不可再次进入。')
            session['candidate_name'] = name
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='姓名或密码错误')
    return render_template('login.html', error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    config = QUESTION_CONFIG
    return render_template('index.html',
                           candidate_name=session.get('candidate_name'),
                           single_count=config['single']['count'],
                           multi_count=config['multiple']['count'],
                           text_count=config['text']['count'])

@app.route('/start', methods=['POST'])
def start_exam():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    name = session.get('candidate_name')
    if session.get(f'exam_done_{name}', False):
        return redirect(url_for('result'))
    if session.get('exam_started', False):
        return redirect(url_for('exam'))
    
    paper = generate_paper()
    session['exam_paper'] = paper
    session['exam_started'] = True
    return redirect(url_for('exam'))

@app.route('/exam')
def exam():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    name = session.get('candidate_name')
    if session.get(f'exam_done_{name}', False):
        return redirect(url_for('result'))
    if not session.get('exam_started', False):
        return redirect(url_for('index'))
    paper = session.get('exam_paper')
    if not paper:
        return redirect(url_for('index'))
    return render_template('exam.html', questions=paper, candidate_name=name)

@app.route('/submit', methods=['POST', 'GET'])
def submit():
    if request.method == 'GET':
        return redirect(url_for('login'))
    
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    name = session.get('candidate_name')
    paper = session.get('exam_paper')
    if not paper:
        return redirect(url_for('index'))
    
    session[f'exam_done_{name}'] = True
    session['exam_started'] = False
    
    total_score = 0.0
    results = []
    
    for idx, q in enumerate(paper):
        q_type = q.get('type', 'single')
        user_ans = request.form.get(f'q_{idx}', '').strip()
        max_score = QUESTION_CONFIG[q_type]['score']
        
        if q_type == 'single':
            is_correct = check_single(user_ans, q['answer'])
            score_earned = max_score if is_correct else 0
            correct_answer = q['answer']
        elif q_type == 'multiple':
            is_correct = check_multiple(user_ans, q['answer'])
            score_earned = max_score if is_correct else 0
            correct_answer = q['answer']
        elif q_type == 'text':
            keywords = q.get('keywords', [])
            score_earned = check_text(user_ans, keywords, max_score)
            is_correct = score_earned >= (max_score * 0.6)
            correct_answer = q.get('answer', '')
        else:
            is_correct = False
            score_earned = 0
            correct_answer = ''
        
        total_score += score_earned
        
        results.append({
            'question': q['question'],
            'type': q_type,
            'your_answer': user_ans if user_ans else '未作答',
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'score_earned': round(score_earned, 2),
            'max_score': max_score
        })
    
    final_score = round(total_score, 2)
    session['exam_result'] = {
        'score': final_score,
        'total': 100,
        'results': results
    }
    return redirect(url_for('result'))

@app.route('/result')
def result():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    name = session.get('candidate_name')
    if not session.get(f'exam_done_{name}', False):
        return redirect(url_for('index'))
    result_data = session.get('exam_result')
    if not result_data:
        return redirect(url_for('index'))
    return render_template('result.html',
                           candidate_name=name,
                           score=result_data['score'],
                           total=result_data['total'],
                           results=result_data['results'])

if __name__ == '__main__':
    app.run(debug=True)
