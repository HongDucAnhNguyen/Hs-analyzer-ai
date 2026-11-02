ifndef u
u:=truong95k58
endif

ifndef env
env:=dev
endif

deploy:
	ssh -i /Users/sotatek/.ssh/id_ecdsa_truong95k58 $(u)@$(h) "mkdir -p $(dir)"
	rsync -avhzL --delete \
				-e "ssh -i /Users/sotatek/.ssh/id_ecdsa_truong95k58" \
				--no-perms --no-owner --no-group \
				--exclude .git \
				--exclude .idea \
				--exclude .env \
				--exclude out \
				--exclude data_ver2 \
				--exclude logs \
				--exclude __pycache__ \
				--exclude classification/.venv \
				--exclude .venv \
				. $(u)@$(h):$(dir)/

restart-app:
	ssh -i /Users/sotatek/.ssh/id_ecdsa_truong95k58 $(u)@$(h) "cd $(dir) && ./stop_all.sh && ./start_all.sh"

deploy-classify-dev:
	make deploy h=34.143.173.34 dir=/home/truong95k58/smart-hs-code-search-ai/classifier_service && make restart-app h=34.143.173.34 dir=/home/truong95k58/smart-hs-code-search-ai/classifier_service

deploy-classify-dev-old:
	make deploy h=34.126.88.217 dir=/home/truong95k58/smart-hs-code-search-ai/classifier_service && make restart-app h=34.126.88.217 dir=/home/truong95k58/smart-hs-code-search-ai/classifier_service
