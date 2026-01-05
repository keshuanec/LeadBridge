web: gunicorn leadbridge.wsgi --bind 0.0.0.0:$PORT --log-file -
release: python manage.py migrate --noinput
build: python manage.py collectstatic --noinput