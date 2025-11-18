"""Tests for MySQL database connectivity and operations in ALFR3D."""
import pytest
import pymysql
import json

def test_mysql_connection(mysql_config):
    """Test connecting to MySQL database."""
    conn = pymysql.connect(**mysql_config)
    assert conn.open, "Failed to connect to MySQL"
    conn.close()

def test_mysql_select(mysql_config):
    """Test selecting data from MySQL tables."""
    conn = pymysql.connect(**mysql_config)
    cursor = conn.cursor()

    # Test select from states table
    cursor.execute("SELECT * FROM states")
    states = cursor.fetchall()
    assert len(states) > 0, "No states found"
    assert states[0][1] == "offline", "First state should be offline"

    # Test select from user_types
    cursor.execute("SELECT * FROM user_types")
    types = cursor.fetchall()
    assert len(types) > 0, "No user types found"

    cursor.close()
    conn.close()

def test_mysql_insert_query(mysql_config):
    """Test inserting and querying data."""
    conn = pymysql.connect(**mysql_config)
    cursor = conn.cursor()

    # Insert a test user (but avoid duplicates, use a unique name)
    test_username = "test_user_12345"
    cursor.execute("SELECT * FROM user WHERE username = %s", (test_username,))
    if cursor.fetchone():
        # Delete if exists
        cursor.execute("DELETE FROM user WHERE username = %s", (test_username,))
        conn.commit()

    # Get required IDs
    cursor.execute("SELECT id FROM states WHERE state = 'offline'")
    state_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM user_types WHERE type = 'guest'")
    type_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM environment WHERE name = 'test'")
    env_id = cursor.fetchone()[0]

    # Insert
    cursor.execute(
        "INSERT INTO user (username, last_online, state, type, environment_id) VALUES (%s, NOW(), %s, %s, %s)",
        (test_username, state_id, type_id, env_id)
    )
    conn.commit()

    # Query back
    cursor.execute("SELECT * FROM user WHERE username = %s", (test_username,))
    user = cursor.fetchone()
    assert user is not None, "User not inserted"
    assert user[1] == test_username, "Username mismatch"

    # Clean up
    cursor.execute("DELETE FROM user WHERE username = %s", (test_username,))
    conn.commit()

    cursor.close()
    conn.close()


def test_mysql_frontend_integration(frontend_client, mysql_config):
    """Test MySQL integration with frontend dashboard."""
    # Test that frontend can retrieve MySQL data
    response = frontend_client.get('/dashboard/data')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert 'mysql' in data
    assert 'connections' in data['mysql']

    # Test database pages load
    response = frontend_client.get('/users')
    assert response.status_code == 200
    assert b'Users' in response.data

    response = frontend_client.get('/devices')
    assert response.status_code == 200
    assert b'Devices' in response.data

    response = frontend_client.get('/environment')
    assert response.status_code == 200
    assert b'Environment' in response.data

    # Test user creation via frontend (integration test)
    response = frontend_client.post('/user/add', data={
        'username': 'mysql_test_user',
        'email': 'mysql@test.com',
        'type': 'guest'
    })
    # Should succeed or redirect
    assert response.status_code in [200, 302]

    # Verify user was created in database
    conn = pymysql.connect(**mysql_config)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user WHERE username = %s", ('mysql_test_user',))
    user = cursor.fetchone()
    assert user is not None, "User not created via frontend"

    # Clean up
    cursor.execute("DELETE FROM user WHERE username = %s", ('mysql_test_user',))
    conn.commit()
    cursor.close()
    conn.close()