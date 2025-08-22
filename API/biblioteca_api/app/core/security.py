# app/core/security.py
from datetime import datetime, timedelta
from typing import Any, Union, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

class AuthenticationService:
    """
    Serviço de autenticação com JWT para APIs REST.
    
    CONCEITOS IMPLEMENTADOS:
    - Geração e validação de JWT tokens
    - Hash seguro de senhas com bcrypt
    - Refresh token mechanism
    - Role-based access control (RBAC)
    """
    
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """
        CONFIGURAÇÃO SEGURA: Inicializa serviço com parâmetros criptográficos.
        
        SECURITY NOTES:
        - secret_key deve ser forte (256+ bits)
        - algorithm HS256 é adequado para single-service
        - Para microservices, considerar RS256 (assinatura assimétrica)
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.bearer = HTTPBearer(auto_error=False)
    
    def create_access_token(
        self, 
        data: dict, 
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        GERAÇÃO DE TOKEN: Cria JWT com claims personalizados.
        
        ESTRUTURA DO TOKEN:
        - sub (subject): user_id
        - exp (expiration): timestamp de expiração
        - iat (issued at): timestamp de criação
        - type: "access" para diferenciação
        - roles: lista de roles do usuário
        """
        to_encode = data.copy()
        
        # CONFIGURAÇÃO DE EXPIRAÇÃO
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)  # Padrão: 15min
        
        # CLAIMS PADRÃO
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        })
        
        # ASSINATURA: Codifica payload com secret
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        logging.info(f"Access token created for user {data.get('sub')}")
        return encoded_jwt
    
    def create_refresh_token(self, user_id: str) -> str:
        """
        REFRESH TOKEN: Token de longa duração para renovação.
        
        SECURITY: Refresh tokens têm menos claims e maior TTL
        """
        data = {
            "sub": user_id,
            "type": "refresh",
            "exp": datetime.utcnow() + timedelta(days=30)  # 30 dias
        }
        
        return jwt.encode(data, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> dict:
        """
        VALIDAÇÃO DE TOKEN: Decodifica e valida JWT.
        
        VALIDAÇÕES:
        - Assinatura válida
        - Token não expirado
        - Formato correto
        - Tipo de token apropriado
        """
        try:
            # DECODIFICAÇÃO: Verifica assinatura e expiração
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm]
            )
            
            # VALIDAÇÃO DE CLAIMS OBRIGATÓRIOS
            user_id = payload.get("sub")
            token_type = payload.get("type")
            
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token inválido: sub claim ausente"
                )
            
            if token_type != "access":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Tipo de token inválido"
                )
            
            return payload
            
        except JWTError as e:
            logging.warning(f"JWT validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido ou expirado",
                headers={"WWW-Authenticate": "Bearer"}
            )
    
    def get_password_hash(self, password: str) -> str:
        """HASH DE SENHA: bcrypt com salt automático."""
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """VERIFICAÇÃO DE SENHA: Compara hash com senha plain."""
        return self.pwd_context.verify(plain_password, hashed_password)

# Instância global do serviço
auth_service = AuthenticationService(secret_key=settings.secret_key)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(auth_service.bearer)
) -> dict:
    """
    DEPENDENCY DE AUTENTICAÇÃO: Extrai e valida usuário atual.
    
    FLUXO:
    1. Extrai token do header Authorization
    2. Valida token JWT
    3. Retorna payload com dados do usuário
    4. Falha com 401 se token inválido
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso requerido",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return auth_service.verify_token(credentials.credentials)

async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    DEPENDENCY DE USUÁRIO ATIVO: Valida se usuário está ativo.
    
    REGRA DE NEGÓCIO: Usuários inativos não podem acessar recursos
    """
    # Em produção, verificar status no banco de dados
    user_id = current_user["sub"]
    
    # Simulação de verificação de usuário ativo
    if not _is_user_active(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inativo"
        )
    
    return current_user

def require_roles(*required_roles: str):
    """
    FACTORY DE DEPENDENCY: Cria dependency para verificação de roles.
    
    USO:
    @app.get("/admin/users")
    async def admin_endpoint(user = Depends(require_roles("admin"))):
        ...
    """
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_roles = current_user.get("roles", [])
        
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado. Roles requeridas: {required_roles}"
            )
        
        return current_user
    
    return role_checker

# EXEMPLOS DE USO EM ENDPOINTS
@app.post("/auth/login")
async def login(credentials: LoginRequest):
    """
    ENDPOINT DE LOGIN: Autentica usuário e retorna tokens.
    
    FLUXO:
    1. Valida credenciais
    2. Gera access e refresh tokens
    3. Retorna tokens + user info
    """
    # VALIDAÇÃO DE CREDENCIAIS
    user = _authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas"
        )
    
    # GERAÇÃO DE TOKENS
    access_token = auth_service.create_access_token(
        data={
            "sub": str(user["id"]),
            "username": user["username"],
            "roles": user["roles"]
        }
    )
    
    refresh_token = auth_service.create_refresh_token(str(user["id"]))
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 900,  # 15 minutos
        "user": {
            "id": user["id"],
            "username": user["username"],
            "roles": user["roles"]
        }
    }

@app.post("/auth/refresh")
async def refresh_access_token(refresh_request: RefreshTokenRequest):
    """
    ENDPOINT DE REFRESH: Renova access token usando refresh token.
    
    SECURITY: Refresh tokens são validados separadamente
    """
    try:
        payload = jwt.decode(
            refresh_request.refresh_token,
            auth_service.secret_key,
            algorithms=[auth_service.algorithm]
        )
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de refresh inválido"
            )
        
        user_id = payload.get("sub")
        user = _get_user_by_id(user_id)
        
        # GERAÇÃO DE NOVO ACCESS TOKEN
        new_access_token = auth_service.create_access_token(
            data={
                "sub": user_id,
                "username": user["username"],
                "roles": user["roles"]
            }
        )
        
        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": 900
        }
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado"
        )

@app.get("/books/admin")
async def admin_books_endpoint(
    current_user: dict = Depends(require_roles("admin", "librarian"))
):
    """
    ENDPOINT PROTEGIDO: Requer roles específicas.
    
    AUTHORIZATION: Apenas admins e bibliotecários podem acessar
    """
    return {
        "message": "Dados administrativos de livros",
        "accessed_by": current_user["username"],
        "roles": current_user["roles"]
    }

@app.get("/profile")
async def get_user_profile(current_user: dict = Depends(get_current_active_user)):
    """
    ENDPOINT DE PERFIL: Requer apenas autenticação básica.
    """
    return {
        "user_id": current_user["sub"],
        "username": current_user["username"],
        "roles": current_user["roles"],
        "authenticated_at": datetime.utcnow().isoformat()
    }