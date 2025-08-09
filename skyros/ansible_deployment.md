# Quick Python Code Deployment to Drones

## Quick Guide

### 1. Preparation

Create an `inventory.ini` file with the list of drones:
```ini
[drones]
drone1 ansible_host=192.168.1.101
drone2 ansible_host=192.168.1.102
drone3 ansible_host=192.168.1.103

[all:vars]
ansible_user=pi
ansible_password=raspberry
ansible_ssh_common_args='-o StrictHostKeyChecking=no'
```

### 2. Code Deployment

```bash
# Copy code folder to all drones
ansible drones -i inventory.ini -m copy -a "src=./your_code_folder dest=/home/pi/"

# Install dependencies
ansible drones -i inventory.ini -m shell -a "cd /home/pi/your_code_folder && pip install -r requirements.txt"

# Install skyros library
ansible drones -i inventory.ini -m shell -a "cd /home/pi/clover-swarm-espnow/skyros && pip install -e ."
```

### 3. Code Execution

```bash
# Run script on all drones simultaneously
ansible drones -i inventory.ini -m shell -a "cd /home/pi/your_code_folder && python your_script.py"

# Or run in background
ansible drones -i inventory.ini -m shell -a "cd /home/pi/your_code_folder && nohup python your_script.py > output.log 2>&1 &"
```

### 4. Monitoring

```bash
# Check process status
ansible drones -i inventory.ini -m shell -a "ps aux | grep python"

# View logs
ansible drones -i inventory.ini -m shell -a "tail -f /home/pi/your_code_folder/output.log"
```

### 5. Stopping

```bash
# Stop all Python processes
ansible drones -i inventory.ini -m shell -a "pkill -f your_script.py"
```

## Advanced Usage

For more complex deployment scenarios, automation, and configuration management, refer to:

- [Official Ansible Documentation](https://docs.ansible.com/)
- [Playbook Guide](https://docs.ansible.com/ansible/latest/playbook_guide/)
- [Configuration Management](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/template_module.html)

## Playbook Examples

Create `deploy.yml`:
```yaml
---
- hosts: drones
  tasks:
    - name: Copy code
      copy:
        src: ./your_code_folder
        dest: /home/pi/
    
    - name: Install dependencies
      pip:
        requirements: /home/pi/your_code_folder/requirements.txt
    
    - name: Start application
      shell: |
        cd /home/pi/your_code_folder
        nohup python your_script.py > output.log 2>&1 &
```

Run: `ansible-playbook -i inventory.ini deploy.yml`
