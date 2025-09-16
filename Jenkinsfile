pipeline {
  agent any
  parameters {
    string(name: 'DEVICES', defaultValue: '', description: 'Comma/space separated device IPs')
    string(name: 'AUTH_TXT', defaultValue: '', description: 'Auth header value')
    string(name: 'COOKIE_TXT', defaultValue: '', description: 'Cookie header value')
    choice(name: 'TEST_TARGET', choices: ['auto','tests_mtr','tests_zoom','tests_oobe'], description: '')
  }
  environment {
    DEVICES   = "${params.DEVICES}"
    AUTH_TXT  = "${params.AUTH_TXT}"
    COOKIE_TXT= "${params.COOKIE_TXT}"
    SEVEN_ZIP = "C:\\Program Files\\7-Zip\\7z.exe"
  }
  stages {
    stage('Write runtime config from params') {
      steps {
        bat 'if not exist config mkdir config'
        writeFile file: 'config/auth.txt',   text: env.AUTH_TXT ?: ''
        writeFile file: 'config/cookie.txt', text: env.COOKIE_TXT ?: ''
      }
    }
    stage('Run tests (serial)') {
      steps {
        script {
          if (!params.DEVICES?.trim()) {
            error("DEVICES parameter is empty")
          }
        }
        bat """
          call .venv\\Scripts\\activate.bat
          set DEVICES=${env.DEVICES}
          set TEST_TARGET=${params.TEST_TARGET}
          set SEVEN_ZIP=${env.SEVEN_ZIP}
          .venv\\Scripts\\python.exe tests_run.py
        """
      }
    }
    stage('Run tests (parallel by device)') {
      when { expression { params.DEVICES?.trim() } }
      steps {
        script {
          def ips = params.DEVICES.trim().split(/[ ,;]+/) as List
          def branches = [:]
          ips.each { ip ->
            branches["run_${ip}"] = {
              bat """
                call .venv\\Scripts\\activate.bat
                set DEVICES=${ip}
                set TEST_TARGET=${params.TEST_TARGET}
                set SEVEN_ZIP=${env.SEVEN_ZIP}
                .venv\\Scripts\\python.exe tests_run.py
              """
            }
          }
          parallel branches
        }
      }
    }
  }
  post {
    always {
      junit allowEmptyResults: true, testResults: 'reports/**/*.xml'
    }
    failure {
      echo '❌ Build failed—see Console Output for the first error.'
    }
  }
}
