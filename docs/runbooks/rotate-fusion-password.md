```shell
# From Laptop (local machine):
ssh prismdev@52.156.104.21
password: Mylife@2026!

# on the VM
cd ~/spire

# update the three Fusion fields
sed -i "s|^    base_url: '.*'|    base_url: 'https://fa-euth-dev20-saasfademo1.ds-fa.oraclepdemos.com'|" personas.yaml
sed -i "s|^    username: '.*'|    username: 'bhagavan'|" personas.yaml
sed -i "s|^    password: '.*'|    password: 'xxxxxx'|" personas.yaml
chmod 644 personas.yaml

##### verify (lengths only)
awk -F"'" '/^    base_url:/{print "base_url len:", length($2)}' personas.yaml
awk -F"'" '/^    username:/{print "username   :", $2}' personas.yaml
awk -F"'" '/^    password:/{print "password len:", length($2)}' personas.yaml

# restart SPIRE
./spire-docker.sh --restart
sleep 20

# check
docker ps --filter name=spire- --format '  {{.Names}}  {{.Status}}' | sort
curl -s http://127.0.0.1:5001/status | python3 -m json.tool
curl -s -X POST http://127.0.0.1:5001/prompt -H 'content-type: application/json' -d '{"prompt":"Count of suppliers"}'

# ngrok status (do not restart unless pgrep prints nothing)
~/ngrok-urls.sh
pgrep -af 'ngrok start'
```